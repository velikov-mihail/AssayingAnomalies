function [center_index, obj_fcn, U] = stepkm(center_index, distmat)
%STEPKM One step in k-means clustering.
%	[CENTER, ERR] = STEPKM(CENTER, DATA)
%	performs one iteration of k-means clustering, where
%
%	DATA: matrix of data to be clustered. (Each row is a data point.)
%	CENTER: center of clusters. (Each row is a center.)
%	ERR: objective function for parititon U.

center_n = length(center_index);
data_n = size(distmat, 1);

% ====== Find the U (partition matrix)
[a,b] = min(distmat(center_index, :));
index = b+center_n*(0:data_n-1);
U = zeros(center_n, data_n);
U(index) = ones(size(index));

% ====== Find the new centers
for i = 1:center_n,
	data_index = find(U(i,:)==1);
	[junk, min_index] = min(sum(distmat(data_index, data_index)));
	center_index(i) = data_index(min_index); 
end

% ====== Find the new objective function
obj_fcn = sum(sum((distmat(center_index, :).^2).*U));	% objective function
