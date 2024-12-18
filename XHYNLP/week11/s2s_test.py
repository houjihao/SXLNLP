import torch
import torch.nn as nn
import numpy as np
import math
import random
import os
import re
from transformers import BertModel, BertConfig, BertTokenizer
import json
"""
基于pytorch的BERT语言模型
"""
bert_path = r"models/bert"
class BERTLanguageModel(nn.Module):
    def __init__(self, config):
        super(BERTLanguageModel, self).__init__()
        bert_config = BertConfig.from_pretrained(config["pretrained_model_name"])
        self.bert = BertModel.from_pretrained(config["pretrained_model_name"], config=bert_config)
        self.classify = nn.Linear(bert_config.hidden_size, bert_config.vocab_size)
        self.dropout = nn.Dropout(0.1)
        self.loss = nn.CrossEntropyLoss()

    # 当输入真实标签，返回loss值；无真实标签，返回预测值
    def forward(self, x, y=None, attention_mask=None):
        # print(x.shape)
        # print(attention_mask.shape)
        
        
        if y is not None:
            outputs= self.bert(x, attention_mask=attention_mask)
            sequence_output = outputs.last_hidden_state
            sequence_output = sequence_output[:, 1:-1, :]
            y_pred = self.classify(sequence_output)
            # 将输出和目标形状调整为 (batch_size * seq_len, vocab_size)
            y_pred = y_pred.view(-1, y_pred.size(-1))
            y = y.view(-1)
            # print(x.size(),y.size(),y_pred.size())
            return self.loss(y_pred, y)
        else:
            outputs= self.bert(x)
            sequence_output = outputs.last_hidden_state
            sequence_output = sequence_output[:, 1:-1, :]
            y_pred = self.classify(sequence_output)
            return torch.softmax(y_pred, dim=-1)

# 加载词表
def build_vocab(vocab_path):
    vocab = {"<pad>": 0}
    with open(vocab_path, encoding="utf8") as f:
        for index, line in enumerate(f):
            char = line[:-1]       # 去掉结尾换行符
            vocab[char] = index + 1 # 留出0位给pad token
    return vocab

# 加载语料
# def load_corpus(path):
#     corpus = ""
#     # with open(path, encoding="gbk") as f:
#     #     for line in f:
#     #         corpus += line.strip()
#     # return corpus
def load_corpus(path):
    corpus = ""
    with open(path, 'r', encoding='utf-8') as file:
        data = json.load(file)
        for item in data:
            if 'title' in item:
                corpus += item['title'] + '[SEP]'
            if 'content' in item:
                corpus += item['content'] + '\\n'                
    return corpus

def create(x):
    cls_index = x.index('[CLS]')
    sep_indices = [i for i, token in enumerate(x) if token == '[SEP]']
    
    first_sep_index = sep_indices[0] if sep_indices else len(x)
    mask = np.zeros((len(x), len(x)))
    
    for i in range(first_sep_index, len(x)):
        mask[i, :i] = 1
        for j in range(i , len(x)):
            mask[j, i] = 1
    for i in range(cls_index, first_sep_index+1):
        mask[i, :first_sep_index+1] = 1
    
    return mask
def padding(x,window_size,):
    pad_token = "[PAD]"
    sequence_length = len(x)
    if sequence_length < window_size:
        padding_length = window_size - sequence_length
        for i in range(padding_length):
            x.append(pad_token)
    # 如果序列长度大于 window_size，则进行截断
    elif sequence_length > window_size:
        x = x[:window_size]
    return x   
# 随机生成一个样本
# 从文本中截取随机窗口，前n个字作为输入，最后一个字作为输出
def build_sample(vocab, tokenizer, window_size, corpus):
    texts = corpus.split('\\n')
    idx =  random.randint(0, len(texts)-1)
    text = texts[idx]
       
    window = text[0:window_size]
    target = text[1:window_size + 1]  # 输入输出错开一位
    # window = [vocab.get(word, vocab["<UNK>"]) for word in window]
    # target = [vocab.get(word, vocab["<UNK>"]) for word in target]
    tokens = tokenizer.tokenize(window)
    tokens = padding(tokens,40)
    tokens = ["[CLS]"] + tokens + ["[SEP]"]
    x = tokenizer.convert_tokens_to_ids(tokens)
    
    tokens_y = tokenizer.tokenize(target)
    tokens_y = padding(tokens_y,40)
    y = tokenizer.convert_tokens_to_ids(tokens_y)
    
    # print(len(x),x)
    # print(len(y),y)
    # 确保 y 的长度与 x 的长度减去 [CLS] 和 [SEP] 后相同
    # assert len(y) == len(x) - 2
    # y = [vocab.get(word, vocab["<UNK>"]) for word in target]
    attention_mask = create(tokens)
    return x, y, attention_mask

# 建立数据集
# sample_length 输入需要的样本数量。需要多少生成多少
# vocab 词表
# window_size 样本长度
# corpus 语料字符串
def build_dataset(sample_length, vocab, tokenizer, window_size, corpus):
    dataset_x = []
    dataset_y = []
    dataset_attention_mask = []
    for i in range(sample_length):
        x, y, attention_mask = build_sample(vocab, tokenizer, window_size, corpus)
        if len(y) == len(x) - 2 :
            dataset_x.append(x)
            dataset_y.append(y)
            dataset_attention_mask.append(attention_mask)
    # print(dataset_x)
    # print(dataset_y)
    # print(dataset_attention_mask)
    return torch.LongTensor(dataset_x), torch.LongTensor(dataset_y), torch.LongTensor(dataset_attention_mask)

# 建立模型
def build_model(config):
    model = BERTLanguageModel(config)
    return model

# 文本生成测试代码
def generate_sentence(openings, model, tokenizer, window_size):
    model.eval()
    with torch.no_grad():
        pred_char = ""
        # 生成了换行符，或生成文本超过20字则终止迭代
        while pred_char != "\n" and len(openings) <= 30:
            openings += pred_char
            tokens = tokenizer.tokenize(openings[-window_size:])
            tokens = ["[CLS]"] + tokens + ["[SEP]"]
            x = tokenizer.convert_tokens_to_ids(tokens)
            x = torch.LongTensor([x])
            if torch.cuda.is_available():
                x = x.cuda()
            y = model(x, attention_mask=[1]*len(x))[0][-1]
            index = sampling_strategy(y)
            pred_char = tokenizer.convert_ids_to_tokens([index])[0]
    return openings

def sampling_strategy(prob_distribution):
    if random.random() > 0.1:
        strategy = "greedy"
    else:
        strategy = "sampling"
    if strategy == "greedy":
        return int(torch.argmax(prob_distribution))
    elif strategy == "sampling":
        prob_distribution = prob_distribution.cpu().numpy()
        return np.random.choice(list(range(len(prob_distribution))), p=prob_distribution)

# 计算文本ppl
def calc_perplexity(sentence, model, tokenizer):
    prob = 0
    model.eval()
    with torch.no_grad():
        tokens = tokenizer.tokenize(sentence)
        tokens = ["[CLS]"] + tokens + ["[SEP]"]
        x = tokenizer.convert_tokens_to_ids(tokens)
        x = torch.LongTensor([x])
        if torch.cuda.is_available():
            x = x.cuda()
        for i in range(1, len(tokens)-1):  # 不考虑 [CLS] 和 [SEP]
            target_index = x[0][i+1].item()
            pred_prob_distribute = model(x[:, :i+1], attention_mask=[1]*(i+1))[0][-1]
            target_prob = pred_prob_distribute[target_index]
            prob += math.log(target_prob, 10)
    return 2 ** (prob * (-1 / (len(tokens) - 2)))

def train(corpus_path, save_weight=True):
    epoch_num = 20        # 训练轮数
    batch_size = 4       # 每次训练样本个数
    train_sample = 100   # 每轮训练总共训练的样本总数
    window_size = 40       # 样本文本长度
    config = {
        "pretrained_model_name": bert_path,
        "vocab_size": None
    }
    vocab = build_vocab("week11/vocab.txt")       # 建立字表
    config["vocab_size"] = len(vocab)
    tokenizer = BertTokenizer.from_pretrained(config["pretrained_model_name"])
    corpus = load_corpus(corpus_path)     # 加载语料
    model = build_model(config)    # 建立模型
    if torch.cuda.is_available():
        model = model.cuda()
    optim = torch.optim.Adam(model.parameters(), lr=0.01)   # 建立优化器
    print("文本词表模型加载完毕，开始训练")
    for epoch in range(epoch_num):
        model.train()
        watch_loss = []
        for batch in range(int(train_sample / batch_size)):
            x, y, attention_mask = build_dataset(batch_size, vocab, tokenizer, window_size, corpus) # 构建一组训练样本
            if torch.cuda.is_available():
                x, y, attention_mask = x.cuda(), y.cuda(), attention_mask.cuda()
            optim.zero_grad()    # 梯度归零
            loss = model(x, y, attention_mask)   # 计算loss
            loss.backward()      # 计算梯度
            optim.step()         # 更新权重
            watch_loss.append(loss.item())
        print("=========\n第%d轮平均loss:%f" % (epoch + 1, np.mean(watch_loss)))
        print(generate_sentence("中国北斗正式提供区域服务", model, tokenizer, window_size))
        print(generate_sentence("购房新政的出台", model, tokenizer, window_size))
    if not save_weight:
        return
    else:
        base_name = os.path.basename(corpus_path).replace("txt", "pth")
        model_path = os.path.join("model", base_name)
        torch.save(model.state_dict(), model_path)
        return
    
if __name__ == "__main__":
    # build_vocab_from_corpus("corpus/all.txt")
    train("week11/sample_data.json", False)