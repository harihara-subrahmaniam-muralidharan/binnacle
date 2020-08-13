#!/usr/bin/env python
# coding: utf-8

# In[1]:


import numpy as np
import pandas as pd
import networkx as nx
from os import mkdir
from os.path import isdir
from copy import deepcopy
from random import choice
from scipy.stats import norm
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

# <h2>Computing Global Coordinates</h2>
# <ol> 
#     <li>This function computes the global coordinate system for the scaffold(connected component) based on the length of the contigs in the connected component and the linking information as returned by MetaCarvel. We order the contigs based on the topological sort of the subgraph and assign coordinates in the global coorinate system in breadth first manner.</li>   
#     <li>We also consider the contig orientations and the edge orientations in accurate estimation of coordinates. </li>
#     <li>If there multiple possible assignments we pick the one that has the largest coordinate value. We choose the greedy approaach because the number of solutions grows exponentially and the problem is NP-Hard! </li>
#     <li>Finally, we normalize all other positions based on the least cooridnate value so that the coorinate system starts with 0.</li>
#     <li>The input to the program is the connected component subgraph of the assembly graph ``oriented.gml" which is a result of running MetaCarvel.</li>
# </ol>

# In[2]:

def Return_Starting_Point(subgraph):
    nodes = list(subgraph.nodes())
    min_node, min_indegree = '', np.inf
    for n in nodes:
        if subgraph.in_degree(n) < min_indegree and subgraph.out_degree(n) > 0:
            min_node, min_indegree = n, subgraph.in_degree(n)
    return min_node, min_indegree

def Random_Simplify(subgraph_, min_indegree_node):
    subgraph = deepcopy(subgraph_)
    cycles = nx.simple_cycles(subgraph)
    edges_removal_set = []
    for c in cycles:
        edge = (c[-1], c[0])
        edges_removal_set += [edge]
    edges_removal_set = set(edges_removal_set)
    subgraph.remove_edges_from(list(edges_removal_set))
    return subgraph

def Compute_Global_Coordinates(subgraph, v_0):
    v_0_orientation = subgraph.nodes[v_0]['orientation']
    v_0_length = int(subgraph.nodes[v_0]['length'])
    if v_0_orientation == 'FOW':
        start = 0
        end = start + v_0_length
    elif v_0_orientation == 'REV':
        start = 0
        end = start-v_0_length
    global_coords = {v_0 : (start,end)}
    nodes = list(subgraph.nodes())
    visited = dict(zip(nodes, [False]*len(nodes)))
    Q = [v_0]
    g_undir = subgraph.to_undirected()
    
    while len(Q) > 0:
        src = Q.pop()
        visited[src] = True
        neighbors = list(g_undir.neighbors(src))
        for n in neighbors:
            if subgraph.has_edge(src,n):
                ###Estimate n's coordinates based on the conting ordering src,n
                edge = (src, n)
                edge_orientation = subgraph.edges[edge]['orientation']
                edge_overlap = int(float(g_undir.edges[edge]['mean']))
                c2_length = int(g_undir.nodes[n]['length'])
                s1, e1 = global_coords[src]
                if edge_orientation == 'EE':
                    e2 = e1 + edge_overlap
                    s2 = e2 + c2_length
                if edge_orientation == 'EB':
                    s2 = e1 + edge_overlap
                    e2 = s2 + c2_length
                if edge_orientation == 'BB':
                    s2 = s1 + edge_overlap
                    e2 = s2 + c2_length
                if edge_orientation == 'BE':
                    e2 = s1 + edge_overlap
                    s2 = e2 + c2_length
                start,end = (s2, e2)
            else:
                ###Estimate n's coordinates based on the conting ordering n,src
                edge = (n,src)
                edge_orientation = subgraph.edges[edge]['orientation']
                edge_overlap = int(float(g_undir.edges[edge]['mean']))
                c1_length = int(g_undir.nodes[n]['length'])
                s2, e2 = global_coords[src]
                if edge_orientation == 'EE':
                    e1 = e2 - edge_overlap
                    s1 = e1 - c1_length
                if edge_orientation == 'EB':
                    e1 = s2 - edge_overlap
                    s1 = e1 - c1_length
                if edge_orientation == 'BB':
                    s1 = s2 - edge_overlap
                    e1 = s1 - c1_length
                if edge_orientation == 'BE':
                    s1 = e2 - edge_overlap
                    e1 = s1 - c1_length
                start,end = (s1,e1)
            try:
                if global_coords[n][0] < start:
                    global_coords[n] = (start,end)
            except KeyError:
                global_coords[n] = (start,end)
            if visited[n] == False:
                visited[n] = True
                Q.append(n)
    ###Normalize for the global coordinate system to start from 0
    min_coord = np.inf
    for g in global_coords:
        start,end = global_coords[g]
        min_val = min(start,end)
        if min_val < min_coord:
            min_coord = min_val
    for g in global_coords:
        s,e = global_coords[g]
        global_coords[g] = s-min_coord, e-min_coord
    return global_coords



# <h2> Computing the Depth of Coverage along the Scaffold's Global Coordinate System  </h2>
# 
# To compute the depth we run the *Compute_Global_Coordinates* and *Load_Read_Coverage* functions and pass this to the *Compute_Coverage* described below. 
#This program estimates the per cooridnate depth by using the outputs of the said two information. 
#The program returns the coverage along the entire scaffold and the coverage along the longest path and a dataframe contiaining the contig, 
#its average depth and its coordinates in the scaffold.   

# In[4]:


def Compute_Coverage(connected_component, df_coverage, start):
    top_sort = list(connected_component.nodes())
    coords = Compute_Global_Coordinates(connected_component, start)
    max_coord = -np.inf
    for c in top_sort:
        max_v = max(coords[c])
        if max_v >= max_coord: max_coord = max_v
    coverage = np.zeros(max_coord+1)
    for c in top_sort:
        contig_depth = np.array(df_coverage.loc[c]['coverage'])
        s,e = coords[c]
        if (s > e): coverage[s:e:-1] += contig_depth
        else: coverage[s:e] += contig_depth
        assert np.abs(s-e) == len(contig_depth), top_sort
    return coverage, coords


# <h2> Change Point Detection on the Scaffold Coverage </h2>
# 
# To compute changepoints along the scaffold we slide a window of default size 1500 along the scaffold and 
#take the ratios of the maximum of means of the window preceeding any point and the window suceeding the point and the minimum of the said quantities. 
#Any abnromal spike magnitude indicates a change point. If the size of the contig is less than the size of the window we adaptively pick a smaller window. 

# In[5]:
def Helper_Changepoints_Z_Stat(cov_vec, window_size=1500):
    indices_non_zero = np.where(cov_vec > 0)
    sliced = cov_vec[indices_non_zero]

    while window_size >= len(sliced)/2:
        window_size = int(window_size/5)

    mean = np.array(pd.Series(sliced).rolling(window_size).mean())[window_size-1:]
    sd = np.array(pd.Series(sliced).rolling(window_size).std())[window_size-1:]

    mu_1, mu_2 = mean[0:len(mean)-window_size-1], mean[window_size+1:]
    sd_1, sd_2 = sd[0:len(sd)-window_size-1],sd[window_size+1:]
    test_stat = [0]*window_size + list((mu_1 - mu_2)/(np.sqrt(sd_1**2+sd_2**2))) + [0]*window_size

    cpts = np.zeros(len(cov_vec))
    cpts[indices_non_zero] = test_stat
    return cpts

def Helper_Changepoints(cov_vec, window_size = 1500):
    indices_non_zero = np.where(cov_vec > 0)
    sliced = cov_vec[indices_non_zero]
    while window_size >= len(sliced)/2:
        window_size = int(window_size/5) 
    temp = np.convolve(sliced, np.ones(window_size), 'valid') / window_size
    Pred, Succ = temp[0:len(temp)-window_size-1],temp[window_size+1:]
    m = np.maximum(Pred, Succ)/np.minimum(Pred, Succ)
    m[m == np.inf] = 0
    mean_ratios = [0]*window_size + list(m) + [0]*window_size
    cpts = np.zeros(len(cov_vec))
    cpts[indices_non_zero] = mean_ratios
    return cpts


# <h2> Outlier Detection in Change Point Signals </h2>
# <ol>
#     <li>The following code segment is used to identify outliers in change points. To do so, we compute the peaks first.</li> 
#     <li>We don't directly identify outliers on the signal because doing so would pickup points near the peaks, these are indicators of sliding windows and not really outliers.</li> 
#     <li>To overcome the issue, we first identify peaks. A point is a peak if a point is larger than its predecessor and successor. This is performed by the function *ID_Peaks*.</li> 
#     <li>The output of this passed to *ID_outliers* which picks all those points that is gretaer than the point which is the *thresh*'s percentile. The default value of *thresh* is 98.5. </li>
#     <li>The filter outliers is still a work in progress. This is aimed at removing all the outliers points that is close to one another, but this is not super important. While the mthod described in the following block is data driven we are working on improving this method by examining the underlying graph structure.</li>
# </ol>

# In[6]:


def ID_outliers(change_point_vec, thresh):
    cutoff_upper = np.percentile(change_point_vec, thresh)
    cutoff_lower = np.percentile(change_point_vec, 100-thresh)
    indices = np.where(((change_point_vec >= cutoff_upper) | (change_point_vec <= cutoff_lower)))
    return indices[0]

def ID_Peaks(change_point_vec, thresh=99):
    left_shift, curr_vec, right_shift = change_point_vec[0:-2], change_point_vec[1:-1], change_point_vec[2:]
    left_diff, right_diff = curr_vec - left_shift, curr_vec - right_shift
    Peak_Indices = np.array(list(set(np.where(left_diff >= 0)[0]).intersection(set(np.where(right_diff >= 0)[0]))))+1
    Peak_Indices = np.sort(list(set(Peak_Indices) - set(np.where(change_point_vec <= 0)[0])))
    Peak_Values = change_point_vec[Peak_Indices]
    outlier_peaks = ID_outliers(Peak_Values, thresh)
    return Peak_Indices[outlier_peaks]

def Filter_Neighbors(outlier_list, changepoints, window_size = 100):
    if len(outlier_list) == 0:
        return outlier_list
    filtered_outlier_list = []
    cmp = outlier_list[0]
    outlier_set = set({cmp})
    for i in range(1, len(outlier_list)):
        curr = outlier_list[i]
        if (curr - cmp) <= window_size:
            if changepoints[curr] >= changepoints[cmp]:
                outlier_set.remove(cmp)
                outlier_set.update([curr])
                cmp = curr
            else:
                outlier_set.update([cmp])
        else:
            outlier_set.update([curr])
            cmp = curr
    outlier_set = list(outlier_set)
    outlier_set.sort()
    return outlier_set


# <h2> Rules for delinking contigs at change points. </h2> 
# 
# The rules for delinking the contigs are described below. The first row represent the orientation of the contig and the first colum represent the location of the contig relative to the contig at the change point. 
# 
# |#                   |  Forward            |  Reverse          |
# |:------------------:|---------------------|-------------------|
# |        Start       | Delink predecessor  | Delink successor  |
# |          End       | Delink successor    | Delink predecessor|
# 
# The input to the program is the set of outliers, the dictionary containing the contigs at each position, a vector of means for detecting change points and a *pos_cutoff* that specifies the number of basepairs from the contig ends to considered for delinking.

# In[7]:


def Get_Outlier_Contigs(outliers, positions, coordinates, graph, pos_cutoff = 100):
    g_ = deepcopy(graph)
    potential_contigs_removal = {}
    for o in outliers:
        try:
            contigs_intersecting = positions[o]
        except KeyError:
            print('KeyError', o, np.max(positions.keys()))
            continue
        closest_contig, closest_contig_val = '',np.inf
        forward, start = True, True
        for contig in contigs_intersecting:
            s,e = coordinates[contig]
            if s>e: f = False
            else: f = True
                
            if np.abs(s-o) < closest_contig_val:
                closest_contig_val= np.abs(s-o) 
                closest_contig = contig
                forward = f
            if np.abs(e-o) < closest_contig_val:
                closest_contig_val= np.abs(e-o) 
                closest_contig = contig
                forward = f
                start = False
        if closest_contig_val <= pos_cutoff:
            potential_contigs_removal[closest_contig] = (closest_contig_val, o, forward, start)
    
    for c in potential_contigs_removal:
        p = potential_contigs_removal[c]
        fwd, start = p[2], p[3]       
        if(fwd == True) and (start == True): 
            #print('Removing',c,'\'s Predecessors')
            predecessors = list(g_.predecessors(str(c)))
            if len(predecessors) > 0:
                edges = [(pred,c) for pred in predecessors]
                g_.remove_edges_from(edges)
        if(fwd == False) and (start == True): 
            #print('Removing',c,'\'s Successors')
            successors = list(g_.successors(str(c)))
            if len(successors) > 0:
                edges = [(c,succ) for succ in successors]
                g_.remove_edges_from(edges)
        if(fwd == False) and (start == False): 
            #print('Removing',c,'\'s Predecessors')
            predecessors = list(g_.predecessors(str(c)))
            if len(predecessors) > 0:
                edges = [(pred,c) for pred in predecessors]
                g_.remove_edges_from(edges)
        if(fwd == True) and (start == False): 
            #print('Removing',c,'\'s Successors')
            successors = list(g_.successors(str(c)))
            if len(successors) > 0:
                edges = [(c,succ) for succ in successors]
                g_.remove_edges_from(edges)
    return g_
         


# <h2> Visualize the Results </h2>
# 
# In this code fragment we plot two figures, one describing 
# <ol>
#     <li>The Pileup of Contigs</li> 
#     <li>Coverages along the global Coordinate </li> 
#     <li>Change Point Metric </li> 
#     <li>The Coverages of the Various Contigs in the Scaffold</li> 
#     The program calls the methods above to perform the computations. 
# </ol>
# 
# The second figure plots the coverage of a contig with respect to its predecessors and successors. 

# In[31]:

def Return_Contig_Scaffold_Positions(coordinate_dictionary):
    pos_dict = {}
    for c in coordinate_dictionary:
        start, end = coordinate_dictionary[c]
        if start > end: a,b = end, start
        else: a,b = start,end
        for i in range(a, b+1):
            try: pos_dict[i].append(c)
            except KeyError: pos_dict[i] = [c]
    return pos_dict