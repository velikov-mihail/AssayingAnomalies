function center_index = initkm2(distmat, cluster_n, method)
% INITKM2 Find the initial centers for a K-means clustering algorithm. 
%	This function is used in kmeans2.m.

% Roger Jang, 20000206

if nargin==0, selfdemo; return; end

switch method
case 1
% ====== Method 1: Randomly pick cluster_n data points as cluster centers
data_n = size(distmat, 1);
tmp = randperm(data_n);
center_index = tmp(1:cluster_n);

case 2
% ====== Method 2: Choose cluster_n data points closest to the mean vector
[junk, mean_index] = min(sum(distmat));
[a,b] = sort(distmat(mean_index, :));
center_index = b(1:cluster_n);

case 3
% ====== Method 3: Choose cluster_n data points furthest to the mean vector
[junk, mean_index] = min(sum(distmat));
[a,b] = sort(distmat(mean_index, :));
b = fliplr(b);
center_index = b(1:cluster_n);

otherwise
disp(['Unknown method in ', mfilename, '!']);

end

function selfdemo
	data_n = 100;
	data1 = ones(data_n, 1)*[0 0] + randn(data_n, 2)/5;
	data2 = ones(data_n, 1)*[0 1] + randn(data_n, 2)/5;
	data3 = ones(data_n, 1)*[1 0] + randn(data_n, 2)/5;
	data = [data1; data2; data3];
	distmat = vecdist(data);
	cluster_n = 10;

	method = 1;
	center_index = feval(mfilename, distmat, cluster_n, method);
	subplot(2,2,1);
	plot(data(:, 1), data(:, 2), 'o');
	for i = 1:cluster_n,
		line(data(center_index(i), 1), data(center_index(i), 2), ...
			'linestyle', 'none', 'marker', '*', 'color', 'r');
	end
	axis equal;
	title('Random method');

	method = 2;
	center_index = feval(mfilename, distmat, cluster_n, method);
	subplot(2,2,2);
	plot(data(:, 1), data(:, 2), 'o');
	for i = 1:cluster_n,
		line(data(center_index(i), 1), data(center_index(i), 2), ...
			'linestyle', 'none', 'marker', '*', 'color', 'r');
	end
	axis equal;
	title('Centers nearest to the mean');

	method = 3;
	center_index = feval(mfilename, distmat, cluster_n, method);
	subplot(2,2,3);
	plot(data(:, 1), data(:, 2), 'o');
	for i = 1:cluster_n,
		line(data(center_index(i), 1), data(center_index(i), 2), ...
			'linestyle', 'none', 'marker', '*', 'color', 'r');
	end
	axis equal;
	title('Centers farthest to the mean');

