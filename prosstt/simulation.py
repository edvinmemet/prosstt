#!/usr/bin/env python
# coding: utf-8

import numpy as np
import scipy as sp
import pandas as pd
from scipy import spatial
from scipy import signal
from scipy import cluster
from scipy.stats import norm
import matplotlib.pyplot as plt
from matplotlib.colors import LogNorm
from scipy.special import gamma as Gamma
import seaborn as sns
import random as rng
import sys
from itertools import chain
import copy
from collections import defaultdict


def printProgress (iteration, total, prefix = '', suffix = '', decimals = 1, barLength = 100):
	"""
	Call in a loop to create a terminal-friendly text progress bar. Contributed by Greenstick on stackoverflow.com/questions/3173320.
	
	Parameters
	----------
		iteration: int
			Current iteration.
		total: int
			Total iterations.
		prefix: str, optional
			Prefix string.
		suffix: str, optional
			Suffix string.
		decimals: int, optional
			Positive number of decimals in percent complete.
		barLength: int, optional
			Character length of bar.
	"""
	formatStr = "{0:." + str(decimals) + "f}"
	percent = formatStr.format(100 * (iteration / float(total)))
	filledLength = int(round(barLength * iteration / float(total)))
	bar = '█' * filledLength + '-' * (barLength - filledLength)
	sys.stdout.write('\r%s |%s| %s%s %s' % (prefix, bar, percent, '%', suffix)),
	if iteration == total:
		sys.stdout.write('\n')
	sys.stdout.flush()


def random_partition(k, iterable):
	"""
	Random partition in almost equisized groups.
	
	Parameters
	----------
	k: int
		How many partitions to create.
	iterable: array
		The iterable to be partitioned.

	Returns
	-------
	results: list of int lists


	contributed by kennytm on stackoverflow.com/questions/3760752
	"""
	results = [[] for i in range(k)]
	for value in iterable:
		x = rng.randrange(k)
		results[x].append(value)
	return (results)


def negbin(x, theta):
	"""
	Alternative formulation of the negative binomial distribution pmf.

	scipy does not support the extended definition so we have to supply it ourselves.

	Parameters
	----------
	x: int
		The random variable.
	theta: real array [p, r]
		p is the probability of success of the Bernoulli test and r the number of "failures".

	Returns
	-------
	Probability that a discrete random variable is exactly equal to some value.
	"""
	p, r = theta
	return (Gamma(r+x) * (1-p)**r * p**x / (Gamma(r) * sp.special.factorial(x)))


def get_pr(a, b, m):
	"""
	calculate parameters for my_negbin from the mean and variance of the distribution.

	For single cell RNA sequencing data we assume that the distribution of the transcripts is described by a negative binomial where the variance s^2 depends on the mean mu by a relation s^2 = a*mu^2 + b*mu.

	Parameters
	----------
	a: float
		Coefficient for the quardratic term. Dominates for high mean expression.
	b: float
		Coefficient for the linear term. Dominates for low mean expression.
	m: float
		Mean expression of a gene.

	Returns
	-------
	p: float
		The probability of success of the Bernoulli test.
	r: float
		The number of "failures" of the Bernoulli test.
	"""
	s2 = (a*m**2 + b*m)
	p = (s2-m)/s2
	r = (m**2)/(s2-m)
	return p, r


def diffusion(T, allow_negative = False):
	"""
	amortized diffusion process, usually between 0 and 1

	Parameters
	----------
	T: int
		The length of the diffusion process (T steps).

	Returns
	-------
	W: float array
		A diffusion process of length T.
	"""
	V = np.zeros(T)
	W = np.zeros(T)

	W[0] = sp.stats.uniform.rvs()
	V[0] = sp.stats.norm.rvs(loc=0, scale=0.2)

	s_eps = 1/T
	eta = sp.stats.uniform.rvs()

	for t in range(0, T-1):
		W[t+1] = W[t] + V[t]

		epsilon = sp.stats.norm.rvs(loc=0, scale=s_eps)
		# amortize the update
		V[t+1] = 0.95 * V[t] + epsilon - eta*V[t]

		# quality control: we are not (?) allowed to go below 0. If it happens,
		# reverse and dampen velocity
		# if W[t+1] <= 0:
		# 	W[t+1] = W[t]
		# 	V[t+1] = -0.2 * V[t]
	return W


def test_correlation(W, k, cutoff):
	"""
	For a column of a matrix, test if previous columns correlate with it.

	Parameters
	----------
	W: numpy array
		The matrix to test.
	k: int
		Compare columns from 0 to k-1 with column k.
	cutoff: float
		Correlation above the cut-off will be considered too much. Should be between 0 and 1 but is not explicitly tested.
	"""
	for i in range(k-1, 0):
		p = sp.stats.pearsonr(W[k], W[i])
		if p[0] > cutoff:
			return True
	return False


def simulate_W(T, K, cutoff=0.2, maxloops=100):
	"""
	Return K diffusion processes of length T as a matrix.
	
	The result of simulate_W is complementary to simulate_H.

	W encodes how K modules of coexpressed genes will behave through differentiation time. Each matrix W describes one branch of a differentiation tree (between two branch points or between a branch point and an endpoint). W describes the module in terms of relative expression (from 0 to a small positive float, so from a gene not being expressed to a gene being expressed at 2x, 3x of its "normal" level).

	After each new diffusion process is added the function checks whether the new diffusion correlates with any of the older ones. If the correlation is too high (above 0.3 per default), the last diffusion process will be replaced with a new one until one is found that does not correlate with any other columns of W or a suitable replacement hasn't been found after 100 tries.

	Obviously this gets more probable the higher the number of components is - it might be advisable to change the number of maximum loops allowed or the cutoff in order to reduce runtime for a high number of components.

	Parameters
	----------
	T: int
		The length of the branch of the differentiation tree.
	K: int
		The number of components/modules of coexpression that describe the differentiation in this branch of the tree.
	cutoff: float, optional
		Correlation above the cut-off will be considered too much. Should be between 0 and 1 but is not explicitly tested.
	maxloops: int, optional
		The maximum number of times the method will try simulating a new diffusion process that doesn't correlate with all previous ones in W before resetting the matrix and starting over.
	"""
	W = np.zeros((K, T))
	k = 0
	loops = 0
	while k < K:
		W[k] = diffusion(T)

		correlates = test_correlation(W, k, cutoff)
		if correlates:
			# repeat and hope it works better this time
			loops += 1
			continue
		else:
			loops = 0
			k += 1		

		if loops > maxloops:
			# we tried so hard
			# and came so far
			# but in the end
			# it doesn't even matter
			return simulate_W(T)

	return np.transpose(W)


def simulate_H(K, G, groups, a=2, b=2):
	"""
	Return sparse membership matrix for G genes in K groups.

	The result of simulate_H is complementary to simulate_W.

	H encodes how G genes are expressed by defining their membership to K expression modules (coded in a matrix W). H could be told to encode metagenes, as it contains the information about which genes are coexpressed (genes that belong to/are influenced by the same modules). The influence of a module on a gene is measured by a number between 0 and 1, drawn from a (symmetric, if used with default values) beta distribution.

	Parameters
	----------
	K: int
		Number of modules.
	G: int
		Number of genes.
	groups: array of int arrays
		groups[i] contains all genes whose expression is influenced by module i
	a: float
		First shape parameter of beta distribution, should be positive.
	b: float
		Second shape parameter of beta distribution, should be positive.
	"""
	H = np.zeros((K, G))
	
	for k in range(K):
		for g in groups[k]:
			H[k][g] += sp.stats.beta.rvs(a, b)

	return H


def create_groups(K, G):
	"""
	Returns a list of the groups to which each gene belongs.

	Each gene G is assigned one of K possible groups twice (random draw with replacement).
	
	Parameters
	----------
	K: int
		Number of modules.
	G: int
		Number of genes.
	"""
	genes = np.random.permutation(G)
	# we want each gene to appear in two groups, in average.
	# If we draw twice it will happen that some genes will take the same 
	# group twice, but it should not happen too often.
	groups1 = random_partition(K, genes)
	# performing the permutation a second time is necessary, else most genes
	# will be in the same modules and we want to mix more
	genes = np.random.permutation(G)
	groups2 = random_partition(K, genes)
	groups = [[i for subz in z for i in subz] for z in zip(groups1, groups2)]
	return groups


def bifurc_adjust(Mu_bif, Mu):
	"""
	Adjust two matrices so that the last line of one equals the first of the other.

	Move each gene so that its starting mean after the bifurcation is the same as the mean it had just before the bifurcation.

	Parameters
	----------
	Mu_bif: numpy array of shape KxG
		
	Mu: float matrix
	"""
	# dif = Mu[-1] / Mu_bif[0]
	# Mu_bif = Mu_bif * dif
	dif = Mu_bif[0] - Mu[-1]
	Mu_bif = Mu_bif - dif
	# Mu_bif[Mu_bif < 0] = 0.1
	return Mu_bif


def simulate_branching_data(G, tree):
	"""
	Simulate the matrices that describe the branches of the differentiation tree.
	
	In order to simulate a branching differentiation tree we are going to simulate every branch of it as an independent, linear differentiation.

		 --1-
	--0-|	  --3-
		 --2-|
			  --4-

	For each branch we will simulate how K gene modules will behave over T pseudotime units (W). Then we will assign each gene to (in average) 2 modules (H). Multiplying W with H results in a matrix of shape TxG, which describes how each gene behaves during differentiation time. Scaling each column of that matrix with a starting value will convert the gene expression values from relative (0-X% of gene expression level) to absolute.

	In case the user calls this function directly, it is important that the Ts and Ks contained in the tree object are ordered correctly, as each branch can, theoretically have different length and a different expression structure. A tree with 5 branches and a topology [[0,1], [0,2], [2,3], [2,4]] will look like this:

			-- T[1]-
	-T[0]--|		  -- T[3]-
			-- T[2]--|
					  -- T[4]-
	timezones:
	---0---|----1----|----2----

	and should have the appropriate K, T values at the correct positions.

	It is recommended that branches at the same timezone have the same length (pseudotime duration T), or failing that at least comparable lengths, as the diffusion processes that govern how the mean expression levels of genes move (and that are crucial for separating the cells after dimensionality reduction) move in small increments, and thus need some time to separate branches from each other.

	Parameters
	----------
	G: int
		Number of genes.
	tree: Tree object
		Contains information about the topology of the tree that is to be simulated: the pseudotime units
	"""
	branches = tree.branches
	Ts = tree.time
	Ks = tree.modules
	lengths = [len(Ts), len(Ks)]
	
	if not all([l == branches for l in lengths]):
		print("the parameters are not enough for %i branches" % branches)
		sys.exit(1)

	# define the W, H and Mu matrix containers for all branches
	Ws = [np.zeros((Ts[i], Ks[i])) for i in range(branches)]
	Hs = [np.zeros((Ks[i], G)) for i in range(branches)]
	Ms = [np.zeros((Ts[i], G)) for i in range(branches)]

	all_groups = []	
	for i in range(branches):
		K = Ks[i]
		T = Ts[i]

		W = simulate_W(T, K)
		groups = create_groups(K, G)
		H = simulate_H(K, G, groups)
		Mu = np.dot(W, H)

		Ws[i] = W
		Hs[i] = H
		Ms[i] = Mu
		all_groups.append(groups)

	for b in tree.topology:
		Ms[b[1]] = bifurc_adjust(Ms[b[1]], Ms[b[0]])

	return Ms, Ws


def sample_data(N, G, Ts, Ms, sample_times, sample_spreads, c_spread=10, alpha=0.3, beta=2, verbose=True):
	"""
	Simulates an NxG count matrix and returns it with the labels and the branch information of the cells.

	Assuming that we know how the mean expression of all genes is supposed to be at any time point of every possible branch of the differentiation (see simulate_branching_data), we can simulate how a real scRNAseq experiment would be conducted - as a time series. We would sample cells from our population at certain sample timepoints. The cells in each sample, since differentiation is asynchronous, would not be at the same differentiation stage, but rather spread around it. Also, while we would try to sample the same number of cells from each time point, this is not possible when using a pipette, so we would expect slight imbalances in the number of cells at each time point.

	The simulation is structured exactly like that: a list of S sample times marks the differentiation stages around which the cells are currently spread. We can control how high this spread is going to be (effectively controlling how synchronous the differentiation goes). We want to "sequence" N cells - that means that we should collect ~N/S cells around each sample time. Then, knowing the duration of each branch/timezone it is easy to decide to which branch each sampled time point belongs to, go to the means matrix of that branch, map the time to a row of the matrix and then use this row as the means of the negative binomial distributions that describe how transcript counts are distributed. Sampling these distributions gives us a realistic cell.

	Along the simulation we can keep the information about the pseudotime of each cell ("labels") as well as which branch each cell is assigned to ("branch").

	Parameters
	----------
	N: int
		Number of cells that should (approximately) be sampled.
	G: int
		Number of genes.
	Ts: int array
		The pseudotime duration of each branch.
	Ms: numpy array
		The matrices that describe how the mean expressions of all genes behave during differentiation time for all branches.
	sample_times: int array
		The pseudotime points around which the cells are sampled.
	sample_spreads: float array
		The variance with which the cells are distributed around the sample points.
	branch_points: int
		The number of branch points in the differentiation tree.
	c_spread: float
		The variance with which we will sample the actual cell numbers around N/S.
	alpha: float
		Coefficient for the quardratic term of the negative binomial variance.
	beta: float
		Coefficient for the linear term of the negative binomial variance.
	verbose: boolean, optional
		If True, run method in verbose mode, printing out a progress bar.

	Returns
	-------
	X: int array
		Simulated single cell RNA seq experiment.
	labels: int array
		The pseudotimes at which each cell was sampled. Corresponds to the rows of X.
	branch:
		The branch of the differentiation tree to which each cell belongs. Corresponds to the rows of X.
	"""
	custm = my_negbin()
	# how many cells do we get from each time point?
	# we want to have ~N cells in the end, so divide N by the sample point size
	n_cells = (N*1.) / len(sample_times)
	cell_spread = np.sqrt(c_spread)
	# we sample n_cells in each sample point, but we lose some for technical reasons
	cells = sp.stats.norm.rvs(loc=n_cells, scale=cell_spread, size=len(sample_times))
	cells = np.abs(cells)
	cells = cells.astype(int)


	# the final result
	X = np.zeros((np.sum(cells), G))

	timestamps = []
	labels = np.zeros(np.sum(cells))
	branch = np.zeros(np.sum(cells))

	# sample from the total time. It starts at 0 and ends at total_time
	total_time = get_max_time(Ts, branch_points)
	for tp, n in zip(sample_times, cells):
		# print(tp, n, total_time)
		timestamps.extend(collect_timestamps(tp, n, total_time))

	# timezone is the part of the tree between two branch points or
	# a branch point and an endpoint
	timezone, offsets = populate_timezone(total_time, Ts, branch_points)

	for n in range(len(timestamps)):
		t = timestamps[n]
		z = int(timezone[t]) # which timezone are we on
		b = pick_branch(z)
		# print(b)
		T_off = offsets[z]
		M = Ms[b]

		# print(t, z, T_off, b)

		for g in range(G):
			try:
				mu = M[t-T_off][g]
			except IndexError:
				mu = M[-1][g]
			p, r = get_pr(a=alpha, b=beta, m=mu)
			X[n][g] = custm.rvs(p, r)
			labels[n] = t
			branch[n] = b

		if verbose:
			printProgress(n, len(timestamps))

	return X, labels, branch

def sample_data_with_absolute_times(n_factor, G, tree, sample_times, alpha=0.3, beta=2, verbose=True):
	"""
	Simulates an NxG count matrix and returns it with the labels and the branch information of the cells.

	This version of the simulation function will sample all time points in "times" n_factor times. This is meant to aid in the development and debugging of the function, as it provides optimal conditions for a smooth tree in G-dimensional space, as it is easy to provide an array 1:T_max and make sure all possible time points are sampled.

	Along the simulation we can keep the information about the pseudotime of each cell ("labels") as well as which branch each cell is assigned to ("branch").

	Parameters
	----------
	n_factor: int
		Number of times to sample each point in times
	G: int
		Number of genes.
	tree: Tree object
		The tree that describes the differentiation procedure.
	alpha: float, optional
		Coefficient for the quardratic term of the negative binomial variance.
	beta: float, optional
		Coefficient for the linear term of the negative binomial variance.
	verbose: boolean, optional
		If True, run method in verbose mode, printing out a progress bar.

	Returns
	-------
	X: int array
		Simulated single cell RNA seq experiment.
	labels: int array
		The pseudotimes at which each cell was sampled. Corresponds to the rows of X.
	branch:
		The branch of the differentiation tree to which each cell belongs. Corresponds to the rows of X.
	"""
	custm = my_negbin()
	# how many cells do we get from each time point?
	# we want to have ~N cells in the end, so divide N by the sample point size
	n_cells = int(n_factor * len(sample_times))

	# the final result
	X = np.zeros((n_cells, G))

	timestamps = np.repeat(sample_times, n_factor)
	labels = np.zeros(len(timestamps))
	branch = np.zeros(len(timestamps))

	timezone = tree.populate_timezone()
	branching_times = tree.branch_times()
	assignments = assign_branches(branching_times, timezone)

	for n in range(len(timestamps)):
		t = int(timestamps[n])
		b = pick_branch(t, timezone, assignments)
		T_off = branching_times[b][0]
		M = tree.means[b]

		for g in range(G):
			try:
				mu = M[t-T_off][g]
			except IndexError:
				mu = M[-1][g]
			p, r = get_pr(a=alpha, b=beta, m=mu)
			X[n][g] = custm.rvs(p, r)
			labels[n] = t
			branch[n] = b
			# print(b, end=", ")

		if verbose:
			printProgress(n, len(timestamps))

	return X, labels, branch


def assign_branches(branch_times, timezone):
	res = defaultdict(list)
	for i in range(len(timezone)):
		z = timezone[i]
		for k in branch_times:
			b = branch_times[k]
			if belongs_to(z, b):
				res[i].append(k)
	return res


def belongs_to(timezone, branch):
	return (timezone[0] >= branch[0]) and (timezone[1] <= branch[1])


def pick_branch(t, timezone, assignments):
	b = -1
	for i in range(len(timezone)):
		branch = timezone[i]
		if t >= branch[0] and t <= branch[1]:
			b = i
			break
	possibilities = assignments[b]
	try:
		return rng.choice(possibilities)
	except IndexError:
		print(t)
		print(timezone)
		print(assignments)


def collect_timestamps(timepoint, n, Tmax, t_s=4):
	"""
	Samples around a timepoint.

	This function simulates how a differentiating cell population would look at a time point when the mean differentiation stage would be at pseudotime t, with cells be spread around t. Since we are sampling a discrete space we need to round the samples. We can control the asynchronicity via the variance of the normal distribution.
	
	Parameters
	----------
	timepoint: int
		The pseudotime point that represents the current mean differentiation stage of the population.
	n: int
		How many cells to sample.
	Tmax: int
		All time points that exceed the differentiation duration will be mapped to the end of the differentiation.
	t_s: float, optional
		Variance of the normal distribution we use to draw pseudotime points. In the experiment metaphor this parameter controls synchronicity.

	Returns
	-------
	timestamps: int array
		Pseudotime points around <timepoint>.
	"""
	timestamps = sp.stats.norm.rvs(loc = timepoint, scale=t_s, size=n)
	timestamps = timestamps.astype(int)
	timestamps[timestamps<0] = 0
	timestamps[timestamps>=Tmax] = Tmax-1
	return timestamps


class my_negbin(sp.stats.rv_discrete):
	"""
	class definition for the alternative negative binomial pmf so that we can sample it using rvs()
	"""
	def _pmf(self, x, p, r):
		theta = [p, r]
		return negbin(x, theta)



def rescale_branch(M_adjust, M_norm):
	adjust_range = np.ptp(M_adjust, axis=0)
	norm_range = np.ptp(M_norm, axis=0)

	# choose the upper threshold for the rescaling
	# should not be <-25% of the branch we adjust to
	upper = np.mean(norm_range)
	lower = upper - upper/4.

	scale_by = np.random.randint(low=lower, high=upper) / scale_to

	# M_adjust = round(apply(data[less,], 1, function(x) rescale(x, to=c(min(x), max(x)*scale_by))))


# worked out kinda ok
def are_lengths_ok(Ms=None, abs_max = 800, rel_dif = 0.3):
	if Ms is None:
		return False
		
	max_crit = False
	rel_crit = False

	maxes = np.array([np.max(np.ptp(x, axis=0)) for x in Ms])
	if np.all(maxes < abs_max):
		max_crit = True

	if np.min(maxes) / np.max(maxes) > rel_dif:
		rel_crit = True
	# print(max_crit, rel_crit)

	# means = [np.mean(np.ptp(x, axis=0)) for x in Ms]
	return (max_crit and rel_crit)


# probably not a very good idea
def transition_adjust(inp_Ma, inp_Mb, transition_length=10):
	Ma = copy.deepcopy(inp_Ma)
	Mb = copy.deepcopy(inp_Mb)
	for i in range(transition_length):
		mbw = 0.5 + i / (transition_length*2) # main branch weight
		Ma[i] = (Ma[i] * mbw + Mb[i] * (1-mbw))
		Mb[i] = (Mb[i] * mbw + Ma[i] * (1-mbw))
	return Ma, Mb


# def smooth_transitions(uMs, branches, tree=None):
# 	for i in range(1, branches):
# 		parallel = 
# 		Ms[i] = transition_adjust(Ms[i], Ms[parallel])