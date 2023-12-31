import sys
import os

import numpy as np
from numpy import linalg as LA
import time
import multiG
import model2 as model
from tester1 import Tester

import torch
import torch.nn as nn

import argparse

# all parameter required
parser = argparse.ArgumentParser(description='JOIE Testing: Type Linking')
parser.add_argument('--modelname', type=str, help='model category', default='./dbpedia')
parser.add_argument('--model', type=str, help='model name including data and model',
                    default="transe_CMP-double_dim1_300_dim2_100_a1_2.5_a2_1.0_m1_0.5_fold_3")
parser.add_argument('--task', type=str, help="tasks", choices=["triple-completion", "entity-typing"],
                    default="triple-completion")
parser.add_argument('--testfile', type=str, help='test data', default="../data/dbpedia/db_onto_small_test.txt")
parser.add_argument('--method', type=str, help='embedding method used')
parser.add_argument('--resultfolder', type=str, help='result output folder', default="dbpedia")
parser.add_argument('--graph', type=str, help='test which graph (ins/onto)', default="onto")
parser.add_argument('--GPU', type=str, default='0', help='GPU ID')
args = parser.parse_args()
os.environ['CUDA_VISIBLE_DEVICES'] = args.GPU

path_prefix = './model/' + args.modelname
hparams_str = args.model
args.method, args.bridge = hparams_str.split('_')[0], hparams_str.split('_')[1]

model_file = path_prefix + "/" + hparams_str + '/' + args.method + '-model-m2.ckpt'
data_file = path_prefix + "/" + hparams_str + '/' + args.method + '-multiG-m2.bin'

test_data = args.testfile
result_folder = './' + args.resultfolder + '/' + args.modelname
result_file = result_folder + "/" + hparams_str + "_graph_" + args.graph + "_result.txt"

torch.manual_seed(0)

if not os.path.exists(result_folder):
    os.makedirs(result_folder)

topK = 10
max_check = 100000

tester = Tester()
tester.build(save_path=model_file, data_save_path=data_file, graph=args.graph, method=args.method, bridge=args.bridge)
if args.task == "triple-completion":
    tester.load_test_link(test_data, max_num=max_check, splitter='\t', line_end='\n')
else:
    tester.load_cross_link(test_data, max_num=max_check, splitter='\t', line_end='\n')

def triple_completion(tester):
    ranks = []
    hit_1 = 0
    hit_10 = 0
    idx = 0
    test_triples = tester.test_triples

    for triple in test_triples:
        idx += 1
        h, r, t = triple
        # LA.norm不能广播

        strr = tester.ent_index2str(t, tester.graph_id)

        # 获得t的列表
        ent_num = tester.joie.num_entsA if tester.graph_id == 1 else tester.joie.num_entsB
        all_ent = np.arange(ent_num)

        th = torch.tensor([h], dtype=torch.long)
        tr = torch.tensor([r], dtype=torch.long)
        tt = torch.tensor([t], dtype=torch.long)
        ta = torch.tensor(all_ent, dtype=torch.long)
        # 计算三元组尾实体为r的打分距离
        dist = tester.dist_source_torch(th, tr, tt, source=args.method)
        # 计算所有尾实体的打分距离
        dist_list = tester.dist_source_torch(th, tr, ta, source=args.method)
        # 计算小于尾实体的实体个数（尾实体排名）
        tail_rank = torch.sum(dist_list <= dist).item()
        ranks.append(tail_rank)

        values, indices = torch.topk(dist_list, topK, largest=False)
        print(values)
        print(indices)

        if tail_rank <= 1 or indices[0].item() in tester.test_hr_map[h][r] \
                or tester.ent_index2str(indices[0], tester.graph_id) == strr:
            hit_1 += 1
        for i in range(topK):
            if tail_rank <= 10 or indices[i].item() in tester.test_hr_map[h][r] \
                    or tester.ent_index2str(indices[i], tester.graph_id) == strr:
                hit_10 += 1
                break

        if idx % 1000 == 0:
            print(np.mean(1 / np.array(ranks)), hit_1 / len(np.array(ranks)), hit_10 / len(ranks))

    # mrr指标
    mrr = np.mean(1 / np.array(ranks))
    # hit@1指标
    hit_1 = hit_1 / len(test_triples)
    # hit@10指标
    hit_10 = hit_10 / len(test_triples)

    print(np.mean(1 / np.array(ranks)), hit_1, hit_10)

    return mrr, hit_1, hit_10


def entity_typing(tester):
    ranks = []
    hit_1 = 0
    hit_3 = 0
    idx = 0
    test_align = tester.test_align

    for align in test_align:
        idx += 1
        e1, e2 = align

        # 这里比的应该是train里的所有onto实体还是test里的onto实体，有可能test中有额外的id吗？
        onto_ent_num = tester.joie.num_entsB
        all_ent = np.arange(onto_ent_num)

        te1 = torch.tensor([e1], dtype=torch.long)
        te2 = torch.tensor([e2], dtype=torch.long)
        ta = torch.tensor(all_ent, dtype=torch.long)

        # la_emb1, la_emb2 = tester.projection_torch(te1, te2, activation=True, bridge="CMP-double")
        # # la_emb1 = la_emb1.unsqueeze(0)
        # # la_emb2 = la_emb2.unsqueeze(0)
        # dist = tester.projection_dist_L2(la_emb1, la_emb2).item()

        la_emb1, la_emb2 = tester.projection_torch(te1, ta, activation=True, bridge="CMP-double")
        dist_list = tester.projection_dist_L2(la_emb1, la_emb2)

        tail_rank = torch.sum(dist_list <= dist_list[te2]).item()
        ranks.append(tail_rank)

        values, indices = torch.topk(dist_list, topK, largest=False)
        print(values)
        print(indices)

        if tail_rank <= 1 or indices[0].item() in tester.lr_map[e1]:
            hit_1 += 1
        for i in range(topK):
            if tail_rank <= 3 or indices[i].item() in tester.lr_map[e1]:
                hit_3 += 1
                break

        if idx % 1000 == 0:
            print(np.mean(1 / np.array(ranks)), hit_1 / len(np.array(ranks)), hit_3 / len(ranks))

    # mrr指标
    mrr = np.mean(1 / np.array(ranks))
    # hit@1指标
    hit_1 = hit_1 / len(test_align)
    # hit@10指标
    hit_3 = hit_3 / len(test_align)

    print(np.mean(1 / np.array(ranks)), hit_1, hit_3)

    return mrr, hit_1, hit_3


if args.task == "triple-completion":
    triple_completion(tester)
elif args.task == "entity-typing":
    entity_typing(tester)
