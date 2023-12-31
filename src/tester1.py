import numpy as np
from numpy import linalg as LA
import heapq as HP
import sys

import multiG
import model2 as model
import trainer2 as trainer
from utils import circular_correlation, np_ccorr

import torch
import torch.nn as nn


class Tester(object):
    def __init__(self):
        self.test_align = None
        self.train_list = None
        self.graph_id = None
        self.graph = None
        self.bridge = None
        self.method = None
        self.b = None
        self.be = None
        self.Me = None
        self.bc = None
        self.Mc = None
        self.joie = None
        self.multiG = None
        self.vec_e = {}
        self.vec_r = {}
        self.mat = np.array([0])
        # below for test data
        self.test_triples = np.array([0])
        self.test_align_rel = []
        self.aligned = {1: set([]), 2: set([])}
        # L1 to L2 map
        self.test_hr_map = {}
        self.test_tr_map = {}
        self.test_ht_map = {}
        # train_map
        self.train_hr_map = {}
        self.train_tr_map = {}
        self.train_ht_map = {}
        # entity map
        self.lr_map = {}

    def build(self, save_path='this-model.ckpt', data_save_path='this-data.bin', graph='ins', method='transe',
              bridge='CG'):
        self.multiG = multiG.multiG()
        self.multiG.load(data_save_path)
        self.method = method  # load
        self.bridge = bridge
        print(self.method, self.bridge)
        assert graph == 'ins' or graph == 'onto'
        self.graph = graph
        self.graph_id = 1 if graph == 'ins' else 2
        ####  setup train data map ####
        self.train_list = list(self.multiG.KG1.triples) if graph == 'ins' else list(self.multiG.KG2.triples)
        for triple in self.train_list:
            h, r, t = triple[0], triple[1], triple[2]
            if self.train_hr_map.get(h) is None:
                self.train_hr_map[h] = {}
            if self.train_hr_map[h].get(r) is None:
                self.train_hr_map[h][r] = set([t])
            else:
                self.train_hr_map[h][r].add(t)

            if self.train_tr_map.get(t) is None:
                self.train_tr_map[t] = {}
            if self.train_tr_map[t].get(r) is None:
                self.train_tr_map[t][r] = set([h])
            else:
                self.train_tr_map[t][r].add(h)

            if self.train_ht_map.get(h) is None:
                self.train_ht_map[h] = {}
            if self.train_ht_map[h].get(t) is None:
                self.train_ht_map[h][t] = set([r])
            else:
                self.train_ht_map[h][t].add(r)
        print("Train set mapping setup done!")
        ###############################

        self.joie = model.joie(num_rels1=self.multiG.KG1.num_rels(),
                               num_ents1=self.multiG.KG1.num_ents(),
                               num_rels2=self.multiG.KG2.num_rels(),
                               num_ents2=self.multiG.KG2.num_ents(),
                               method=self.method,
                               bridge=self.bridge,
                               L1=self.multiG.L1)

        self.joie.load_state_dict(torch.load(save_path))

        self.vec_e[1] = self.joie.ht1
        self.vec_e[2] = self.joie.ht2
        self.vec_r[1] = self.joie.r1
        self.vec_r[2] = self.joie.r2

        if self.bridge == "CMP-double":
            self.Mc = self.joie.Mc
            self.bc = self.joie.bc
            self.Me = self.joie.Me
            self.be = self.joie.be
        else:
            self.mat = self.joie.M
            self.b = self.joie.b

    def load_cross_link(self, filename, max_num=10000, splitter='\t', line_end='\n', dedup=True):
        num_lines = 0
        align = []
        dedup_set = set([])
        for line in open(filename):
            if len(align) > max_num:
                break
            if dedup and line in dedup_set:
                continue
            elif dedup:
                dedup_set.add(line)
            line = line.rstrip(line_end).split(splitter)
            if len(line) != 3:
                continue
            num_lines += 1
            e1 = self.multiG.KG1.ent_str2index(line[0])
            e2 = self.multiG.KG2.ent_str2index(line[2])
            if e1 is None or e2 is None:
                continue
            align.append([e1, e2])
            if self.lr_map.get(e1) is None:
                self.lr_map[e1] = set([e2])
            else:
                self.lr_map[e1].add(e2)
            # if self.hr_map.get(e2) is None:
            #     self.test_hr_map[e1] = {}
            # if self.lr_map.get(e2) is None:
            #     self.lr_map[e2] = set([e1])
            # else:
            #     self.lr_map[e2].add(e1)
        self.test_align = np.array(align, dtype=np.int32)
        print("load test data from %s %d out of %d" % (filename, len(align), num_lines))

    def load_test_link(self, filename, max_num=2000, splitter='\t', line_end='\n', dedup=True):
        num_lines = 0
        triples = []
        dedup_set = set([])
        for line in open(filename):
            if len(triples) > max_num:
                break
            if dedup and line in dedup_set:
                continue
            elif dedup:
                dedup_set.add(line)
            line = line.rstrip(line_end).split(splitter)
            if len(line) != 3:
                continue
            num_lines += 1
            if self.graph == 'ins':
                e1 = self.multiG.KG1.ent_str2index(line[0])
                r = self.multiG.KG1.rel_str2index(line[1])
                e2 = self.multiG.KG1.ent_str2index(line[2])
            elif self.graph == 'onto':
                e1 = self.multiG.KG2.ent_str2index(line[0])
                r = self.multiG.KG2.rel_str2index(line[1])
                e2 = self.multiG.KG2.ent_str2index(line[2])
            else:
                raise ValueError('not valid graph')
            if e1 == None or e2 == None or r == None:
                continue
            triples.append([e1, r, e2])

            ###### Set up test map #######
            if self.test_hr_map.get(e1) is None:
                self.test_hr_map[e1] = {}
            if self.test_hr_map[e1].get(r) is None:
                self.test_hr_map[e1][r] = set([e1])
            else:
                self.test_hr_map[e1][r].add(e2)

            if self.test_tr_map.get(e2) is None:
                self.test_tr_map[e2] = {}
            if self.test_tr_map[e2].get(r) is None:
                self.test_tr_map[e2][r] = set([e1])
            else:
                self.test_tr_map[e2][r].add(e1)

            if self.test_ht_map.get(e1) is None:
                self.test_ht_map[e1] = {}
            if self.test_ht_map[e1].get(e2) is None:
                self.test_ht_map[e1][e2] = set([r])
            else:
                self.test_ht_map[e1][e2].add(r)
            ###############################
        self.test_triples = np.array(triples, dtype=np.int32)
        print("test set mapping done!")
        print("Loaded test data from %s, %d out of %d." % (filename, len(triples), num_lines))

    def load_test_data_rel(self, filename, splitter='@@@', line_end='\n'):
        num_lines = 0
        align = []
        for line in open(filename):
            line = line.rstrip(line_end).split(splitter)
            if len(line) != 2:
                continue
            num_lines += 1
            e1 = self.multiG.KG1.rel_str2index(line[0])
            e2 = self.multiG.KG2.rel_str2index(line[1])
            if e1 == None or e2 == None:
                continue
            align.append([e1, e2])
            if self.lr_map_rel.get(e1) == None:
                self.lr_map_rel[e1] = set([e2])
            else:
                self.lr_map_rel[e1].add(e2)
            if self.rl_map_rel.get(e2) == None:
                self.rl_map_rel[e2] = set([e1])
            else:
                self.rl_map_rel[e2].add(e1)
        self.test_align_rel = np.array(align, dtype=np.int32)
        print("Loaded test data (rel) from %s, %d out of %d." % (filename, len(align), num_lines))

    def load_except_data(self, filename, splitter='@@@', line_end='\n'):
        num_lines = 0
        num_read = 0
        for line in open(filename):
            line = line.rstrip(line_end).split(splitter)
            if len(line) != 2:
                continue
            num_lines += 1
            e1 = self.multiG.KG1.ent_str2index(line[0])
            e2 = self.multiG.KG2.ent_str2index(line[1])
            if e1 == None or e2 == None:
                continue
            self.aligned[1].add(e1)
            self.aligned[2].add(e2)
            num_read += 1
        print("Loaded excluded ids from %s, %d out of %d." % (filename, num_read, num_lines))

    def load_align_ids(self, filename, max_num=100000, splitter='@@@', line_end='\n'):
        num_lines = 0
        num_read = 0
        aligned1, aligned2 = set([]), set([])
        for line in open(filename):
            if num_read > max_num:
                break
            line = line.strip().split(splitter)
            if len(line) != 3:
                continue
            num_lines += 1
            if self.graph == 'ins':
                e1 = self.multiG.KG1.ent_str2index(line[0])
                e2 = self.multiG.KG1.ent_str2index(line[2])
            elif self.graph == 'onto':
                e1 = self.multiG.KG2.ent_str2index(line[0])
                e2 = self.multiG.KG2.ent_str2index(line[2])
            else:
                raise ValueError('not valid graph')
            if e1 == None or e2 == None:
                continue
            aligned1.add(e1)
            aligned2.add(e2)
            num_read += 1
        return aligned1, aligned2

    def load_more_truth_data(self, filename, splitter='@@@', line_end='\n'):
        num_lines = 0
        count = 0
        for line in open(filename):
            line = line.rstrip(line_end).split(splitter)
            if len(line) != 2:
                continue
            num_lines += 1
            e1 = self.multiG.KG1.ent_str2index(line[0])
            e2 = self.multiG.KG2.ent_str2index(line[1])
            if e1 == None or e2 == None:
                continue
            if self.lr_map.get(e1) == None:
                self.lr_map[e1] = set([e2])
            else:
                self.lr_map[e1].add(e2)
            if self.rl_map.get(e2) == None:
                self.rl_map[e2] = set([e1])
            else:
                self.rl_map[e2].add(e1)
            count += 1
        print("Loaded extra truth data into mappings from %s, %d out of %d." % (filename, count, num_lines))

    # by default, return head_mat
    def get_mat(self):
        return self.mat

    def ent_index2vec(self, e, source):
        assert (source in set([1, 2]))
        return self.vec_e[source][int(e)]

    def rel_index2vec(self, r, source):
        assert (source in set([1, 2]))
        return self.vec_r[source][int(r)]

    def ent_str2vec(self, str, source):
        KG = None
        if source == 1:
            KG = self.multiG.KG1
        else:
            KG = self.multiG.KG2
        this_index = KG.ent_str2index(str)
        if this_index == None:
            return None
        return self.vec_e[source][this_index]

    def rel_str2vec(self, str, source):
        KG = None
        if source == 1:
            KG = self.multiG.KG1
        else:
            KG = self.multiG.KG2
        this_index = KG.rel_str2index(str)
        if this_index == None:
            return None
        return self.vec_r[source][this_index]

    class index_dist:
        def __init__(self, index, dist):
            self.dist = dist
            self.index = index
            return

        def __lt__(self, other):
            return self.dist > other.dist

    def ent_index2str(self, str, source):
        KG = None
        if source == 1:
            KG = self.multiG.KG1
        else:
            KG = self.multiG.KG2
        return KG.ent_index2str(str)

    def rel_index2str(self, str, source):
        KG = None
        if source == 1:
            KG = self.multiG.KG1
        else:
            KG = self.multiG.KG2
        return KG.rel_index2str(str)

    def ent_str2index(self, str, source):
        KG = None
        if source == 1:
            KG = self.multiG.KG1
        else:
            KG = self.multiG.KG2
        return KG.ent_str2index(str)

    def rel_str2index(self, str, source):
        KG = None
        if source == 1:
            KG = self.multiG.KG1
        else:
            KG = self.multiG.KG2
        return KG.rel_str2index(str)

    # input must contain a pool of vecs. return a list of indices and dist
    def kNN_torch(self, vec, vec_pool, topk=10, self_id=None, except_ids=None, limit_ids=None):
        dist = tester.dist_source_torch(th, tr, tt, source=args.method)
        for i in range(len(vec_pool)):
            # skip self
            if i == self_id or ((not except_ids is None) and i in except_ids):
                continue
            if (not limit_ids is None) and i not in limit_ids:
                continue
            dist = LA.norm(vec - vec_pool[i], ord=(1 if self.multiG.L1 else 2))
            if len(q) < topk:
                HP.heappush(q, self.index_dist(i, dist))
            else:
                # indeed it fetches the biggest
                tmp = HP.nsmallest(1, q)[0]
                if tmp.dist > dist:
                    HP.heapreplace(q, self.index_dist(i, dist))
        rst = []
        while len(q) > 0:
            item = HP.heappop(q)
            rst.insert(0, (item.index, item.dist))
        return rst

    def kNN(self, vec, vec_pool, topk=10, self_id=None, except_ids=None, limit_ids=None):
        q = []
        for i in range(len(vec_pool)):
            # skip self
            if i == self_id or ((not except_ids is None) and i in except_ids):
                continue
            if (not limit_ids is None) and i not in limit_ids:
                continue
            dist = LA.norm(vec - vec_pool[i], ord=(1 if self.multiG.L1 else 2))
            if len(q) < topk:
                HP.heappush(q, self.index_dist(i, dist))
            else:
                # indeed it fetches the biggest
                tmp = HP.nsmallest(1, q)[0]
                if tmp.dist > dist:
                    HP.heapreplace(q, self.index_dist(i, dist))
        rst = []
        while len(q) > 0:
            item = HP.heappop(q)
            rst.insert(0, (item.index, item.dist))
        return rst

    def kNN_link(self, h, r, topk=10, limit_ids=None, is_filtered=True):
        q = []
        cand_scope = limit_ids
        if cand_scope == None:
            cand_scope = range(len(self.vec_e[1])) if self.graph == 'ins' else range(len(self.vec_e[2]))
        for i in cand_scope:
            hasMapping = self.train_hr_map.get(h) is not None and self.train_hr_map[h].get(r) is not None
            if is_filtered and hasMapping and i in self.train_hr_map[h][r]:  # chang to train map
                # print('find in train set (kNN)')
                continue
            dist = self.dist_source(h, r, i, source=self.method)
            if len(q) < topk:
                HP.heappush(q, self.index_dist(i, dist))
            else:
                # indeed it fetches the biggest
                tmp = HP.nsmallest(1, q)[0]
                if tmp.dist > dist:
                    HP.heapreplace(q, self.index_dist(i, dist))
        rst = []
        while len(q) > 0:
            item = HP.heappop(q)
            rst.insert(0, (item.index, item.dist))
        return rst

    def rel_score(self, h, r, t):
        dist = self.dist_source(h, r, t, source=self.method)
        return dist

    def kNN_rels(self, h, t, is_filtered=True):  # no need to limit id
        q = []
        cand_scope = range(len(self.vec_r[1])) if self.graph == 'ins' else range(len(self.vec_r[2]))
        for i in cand_scope:
            hasMapping = self.train_ht_map.get(h) is not None and self.train_ht_map[h].get(t) is not None
            dist = self.dist_source(h, i, t, source=self.method)
            if is_filtered and hasMapping and i in self.train_ht_map[h][t]:
                HP.heappush(q, self.index_dist(i, float('inf')))
            else:
                HP.heappush(q, self.index_dist(i, dist))
        rst = []
        while len(q) > 0:
            item = HP.heappop(q)
            rst.insert(0, (item.index, item.dist))
        return rst

    # input must contain a pool of vecs. return a list of indices and dist
    def NN(self, vec, vec_pool, self_id=None, except_ids=None, limit_ids=None):
        min_dist = sys.maxint
        rst = None
        for i in range(len(vec_pool)):
            # skip self
            if i == self_id or ((not except_ids is None) and i in except_ids):
                continue
            if (not limit_ids is None) and i not in limit_ids:
                continue
            dist = LA.norm(vec - vec_pool[i], ord=(1 if self.multiG.L1 else 2))
            if dist < min_dist:
                min_dist = dist
                rst = i
        return (rst, min_dist)

    # input must contain a pool of vecs. return a list of indices and dist. rank an index in a vec_pool from 
    def rank_index_from(self, vec, vec_pool, index, self_id=None, except_ids=None, limit_ids=None):
        dist = LA.norm(vec - vec_pool[index], ord=(1 if self.multiG.L1 else 2))
        rank = 1
        for i in range(len(vec_pool)):
            if i == index or i == self_id or ((not except_ids is None) and i in except_ids):
                continue
            if (not limit_ids is None) and i not in limit_ids:
                continue
            if dist > LA.norm(vec - vec_pool[i], ord=(1 if self.multiG.L1 else 2)):
                rank += 1
        return rank

    def rank_index_link(self, h, r, t, limit_ids=None, is_filtered=True):
        # choose the smallest one
        cand_scope = limit_ids
        dist_target = self.dist_source(h, r, t, source=self.method)
        '''
        for ti in t_test:
            dist_current = self.dist_source(h, r, ti, source=self.method)
            if dist_current < dist_target:
                dist_target = dist_current
        '''
        if cand_scope == None:
            cand_scope = range(len(self.vec_e[1])) if self.graph == 'ins' else range(len(self.vec_e[2]))
        rank = 1
        for i in cand_scope:
            if i == t:
                continue
            hasMapping = self.train_hr_map.get(h) is not None and self.train_hr_map[h].get(r) is not None
            if is_filtered and hasMapping and i in self.train_hr_map[h][r]:
                # print('find in train set (rank)')
                continue
            if dist_target > self.dist_source(h, r, i, source=self.method):
                rank += 1
        return rank

    # Change if AM changes
    '''
    def projection(self, e, source):
        assert (source in set([1, 2]))
        vec_e = self.ent_index2vec(e, source)
        #return np.add(np.dot(vec_e, self.mat), self._b)
        return np.dot(vec_e, self.mat)
    '''

    def projection_torch(self, e1, e2, activation=True, bridge="CMP-double"):
        vec_e1 = self.vec_e[1][e1]  # instance to onto space
        vec_e2 = self.vec_e[2][e2]
        if activation:
            if bridge == "CMP-double":
                la_emb1 = torch.tanh(torch.matmul(vec_e1, self.Me) + self.be)
                la_emb2 = torch.tanh(torch.matmul(vec_e2, self.Mc) + self.bc)
            else:
                la_emb1 = torch.tanh(torch.matmul(vec_e1, self.mat) + self.b)
                la_emb2 = vec_e2
        else:
            la_emb1 = torch.matmul(vec_e1, self.mat) + self.b
            la_emb2 = vec_e2
        return la_emb1, la_emb2

    def projection_dist_L2(self, la_emb1, la_emb2):
        return torch.norm(la_emb1 - la_emb2, p=2, dim=1)


    def projection(self, e, source, activation=True, bridge="CMP-double"):
        assert (source in set([1, 2]))
        vec_e = self.ent_index2vec(e, source)
        # return np.add(np.dot(vec_e, self.mat), self._b)
        if activation:
            if bridge == "CMP-double":
                return np.tanh(np.dot(vec_e, self.Me))
            return np.tanh(np.dot(vec_e, self.mat))
        else:
            return np.dot(vec_e, self.mat)

    def projection_rel(self, r, source):
        assert (source in set([1, 2]))
        vec_r = self.rel_index2vec(r, source)
        # return np.add(np.dot(vec_e, self.mat), self._b)
        return np.dot(vec_r, self.mat)

    def projection_vec(self, vec, source):
        assert (source in set([1, 2]))
        # return np.add(np.dot(vec_e, self.mat), self._b)
        return np.dot(vec, self.mat)

    # Currently supporting only lan1 to lan2
    def projection_pool(self, ht_vec, bridge="CMP-double"):
        # return np.add(np.dot(ht_vec, self.mat), self._b)
        if bridge == "CMP-double":
            return np.tanh(np.dot(ht_vec, self.Me))
        return np.dot(ht_vec, self.mat)

    def dist_source(self, h, r, t, source='transe'):
        if source == 'transe':
            return self.dist_transe(h, r, t)
        elif source == 'distmult':
            return self.dist_distmult(h, r, t)
        elif source == 'hole':
            return self.dist_hole(h, r, t)
        else:
            raise ValueError('Method invalid! Can not compute distance!')

    def dist_transe(self, h, r, t):
        if self.graph == 'ins':
            h_vec = self.vec_e[1][h]
            t_vec = self.vec_e[1][t]
            r_vec = self.vec_r[1][r]
        else:
            h_vec = self.vec_e[2][h]
            t_vec = self.vec_e[2][t]
            r_vec = self.vec_r[2][r]
        return LA.norm(h_vec + r_vec - t_vec, ord=2)

    def dist_distmult(self, h, r, t):
        if self.graph == 'ins':
            h_vec = self.vec_e[1][h]
            t_vec = self.vec_e[1][t]
            r_vec = self.vec_r[1][r]
        else:
            h_vec = self.vec_e[2][h]
            t_vec = self.vec_e[2][t]
            r_vec = self.vec_r[2][r]
        return -np.dot(r_vec, np.multiply(h_vec, t_vec))  # add minus

    def dist_hole(self, h, r, t):
        if self.graph == 'ins':
            h_vec = self.vec_e[1][h]
            t_vec = self.vec_e[1][t]
            r_vec = self.vec_r[1][r]
        else:
            h_vec = self.vec_e[2][h]
            t_vec = self.vec_e[2][t]
            r_vec = self.vec_r[2][r]
        return -np.dot(np_ccorr(h_vec, t_vec), r_vec)  # add minus

    def dist_source_torch(self, h, r, t, source='transe'):
        if source == 'transe':
            return self.dist_transe_torch(h, r, t)
        elif source == 'distmult':
            return self.dist_distmult_torch(h, r, t)
        elif source == 'hole':
            return self.dist_hole_torch(h, r, t)
        else:
            raise ValueError('Method invalid! Can not compute distance!')

    def dist_transe_torch(self, h, r, t):
        if self.graph == 'ins':
            h_vec = self.joie.ht1[h]
            t_vec = self.joie.ht1[t]
            r_vec = self.joie.r1[r]
        else:
            h_vec = self.joie.ht2[h]
            t_vec = self.joie.ht2[t]
            r_vec = self.joie.r2[r]
        return torch.norm(h_vec + r_vec - t_vec, p=2, dim=1)

    def dist_distmult_torch(self, h, r, t):
        if self.graph == 'ins':
            h_vec = self.joie.ht1[h]
            t_vec = self.joie.ht1[t]
            r_vec = self.joie.r1[r]
        else:
            h_vec = self.joie.ht2[h]
            t_vec = self.joie.ht2[t]
            r_vec = self.joie.r2[r]
        return -torch.dot(r_vec, torch.multiply(h_vec, t_vec))  # add minus

    def dist_hole_torch(self, h, r, t):
        if self.graph == 'ins':
            h_vec = self.joie.ht1[h]
            t_vec = self.joie.ht1[t]
            r_vec = self.joie.r1[r]
        else:
            h_vec = self.joie.ht2[h]
            t_vec = self.joie.ht2[t]
            r_vec = self.joie.r2[r]
        return -torch.dot(np_ccorr(h_vec, t_vec), r_vec)  # add minus TODO
