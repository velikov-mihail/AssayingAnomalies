function [center_index, U, obj_fcn] = kmeans2(distmat, cluster_n, options)
%KMEANS Find clusters with Forgy's batch-mode k-means clustering.
%
%	This function is different from KMEANS in that the given input is
%	a distance matrix instead of a data matrix.
%
%	[CENTER, U, OBJ_FCN] = KMEANS2(DISTMAT, CLUSTER_N) applies
%	Forgy's batch-mode k-means clustering method to a given distance matrix.
%	Input and output arguments of this function are:
%
%		DISTMAT: Distance matrix whose elements are the pairwise
%			distances of the data set to be clustered.
%			The matrix is supposed to symmetric.
%		CLUSTER_N: number of clusters (greater than one)
%		CENTER: final cluster centers, where each row is a center
%		U: final fuzzy partition matrix (or MF matrix)
%		OBJ_FCN: values of the objective function during iterations 
%
%	KMEANS2(DATA, CLUSTER_N, OPTIONS) use an additional argument OPTIONS to
%	control clustering parameters, stopping criteria, and/or iteration
%	info display:
%		
%		OPTIONS(1): max. number of iterations (default: 100) 
%		OPTIONS(2): min. amount of improvement (default: 1e-5)
%		OPTIONS(3): info display during iteration (default: 1)
%	
%	If any entry of OPTIONS is NaN (not a number), the default value is
%	used instead. The clustering process stops when the max. number of
%	iteration is reached, or when the objective function improvement
%	between two consecutive iteration is less than the min. amount of
%	improvement specified.
%	
%	Type "kmeans2" for a self demo.

%	Roger Jang, 20000206

if nargin == 0, selfdemo; return; end
if nargin ~= 2 & nargin ~= 3,
	error('Too many or too few input arguments!');
end

data_n = size(distmat, 1);

% Change the following to set default options
default_options = [ 100;	% max. number of iteration
		1e-5;	% min. amount of improvement
		1];	% info display during iteration 

if nargin == 2,
	options = default_options;
else
	% If "options" is not fully specified, pad it with default values.
	if length(options) < length(default_options),
		tmp = default_options;
		tmp(1:length(options)) = options;
		options = tmp;
	end
	% If some entries of "options" are nan's, replace them with defaults.
	nan_index = find(isnan(options)==1);
	options(nan_index) = default_options(nan_index);
end

max_iter = options(1);		% Max. iteration
min_impro = options(2);		% Min. improvement
display = options(3);		% Display info or not

obj_fcn = zeros(max_iter, 1);	% Array for objective function

center_index = initkm2(distmat, cluster_n, 3);	% Initial center index
% Main loop
for i = 1:max_iter,
	[center_index, obj_fcn(i), U] = stepkm2(center_index, distmat);
	if display, 
		fprintf('Iteration count = %d, obj. fcn = %f\n', i, obj_fcn(i));
	end
	% check termination condition
	if i > 1,
		if abs(obj_fcn(i) - obj_fcn(i-1)) < min_impro, break; end,
	end
end
iter_n = i;	% Actual number of iterations 
obj_fcn(iter_n+1:max_iter) = [];

% ========== subfunctions ==========
function selfdemo
	data_n = 100;
	data1 = ones(data_n, 1)*[0 0] + randn(data_n, 2)/5;
	data2 = ones(data_n, 1)*[0 1] + randn(data_n, 2)/5;
	data3 = ones(data_n, 1)*[1 0] + randn(data_n, 2)/5;
	data = [data1; data2; data3];
	distmat = vecdist(data);

	cluster_n = 3;
	[center_index, U, obj_fcn] = feval(mfilename, distmat, cluster_n);
	plot(data(:, 1), data(:, 2), 'o');
	maxU = max(U);
	index1 = find(U(1, :) == maxU);
	index2 = find(U(2, :) == maxU);
	index3 = find(U(3, :) == maxU);
	line(data(index1, 1), data(index1, 2), ...
		'linestyle', 'none', 'marker', '*', 'color', 'g');
	line(data(index2, 1), data(index2, 2), ...
		'linestyle', 'none', 'marker', '*', 'color', 'r');
	line(data(index3, 1), data(index3, 2), ...
		'linestyle', 'none', 'marker', '*', 'color', 'c');
	axis equal;
