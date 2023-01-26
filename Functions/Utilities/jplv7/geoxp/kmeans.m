function [center, U, distortion] = kmeans(dataSet, clusterNum, plotOpt)
%KMEANS K-means clustering using Forgy's batch-mode method
%	Usage: [center, U, distortion] = KMEANS(dataSet, clusterNum)
%		dataSet: data set to be clustered; where each row is a sample data
%		clusterNum: number of clusters (greater than one)
%		center: final cluster centers, where each row is a center
%		U: final fuzzy partition matrix (or MF matrix)
%		distortion: values of the objective function during iterations 
%
%	Type "kmeans" for a self demo.

%	Roger Jang, 20030330

if nargin==0, selfdemo; return; end
if nargin<3, plotOpt=0; end

maxLoopCount = 100;			% Max. iteration
distortion = zeros(maxLoopCount, 1);	% Array for objective function
center = initCenter(clusterNum, dataSet);	% Initial cluster centers

if plotOpt
	plot(dataSet(:,1), dataSet(:,2), 'b.');
	centerH=line(center(:,1), center(:,2), 'color', 'r', 'marker', 'o', 'linestyle', 'none', 'linewidth', 2);
	axis image
end;

% Main loop
for i = 1:maxLoopCount,
	[center, distortion(i), U] = updateCenter(center, dataSet);
	if plotOpt, 
		fprintf('Iteration count = %d, distortion = %f\n', i, distortion(i));
		set(centerH, 'xdata', center(:,1), 'ydata', center(:,2));
		drawnow;
	end
	% check termination condition
	if i > 1,
		if abs(distortion(i-1) - distortion(i))/distortion(i-1) < eps, break; end,
	end
end
loopCount = i;	% Actual number of iterations 
distortion(loopCount+1:maxLoopCount) = [];

if plotOpt
	color = {'r', 'g', 'c', 'y', 'm', 'b', 'k'};
	figure;
	plot(dataSet(:, 1), dataSet(:, 2), 'o');
	maxU = max(U);
	clusterNum = size(center,1);
	for i=1:clusterNum,
		index = find(U(i, :) == maxU);
		colorIndex = rem(i, length(color))+1;  
		line(dataSet(index, 1), dataSet(index, 2), 'linestyle', 'none', 'marker', '*', 'color', color{colorIndex});
		line(center(:,1), center(:,2), 'color', 'r', 'marker', 'o', 'linestyle', 'none', 'linewidth', 2);
	end
	axis image;
end


% ========== subfunctions ==========
% ====== Find the initial centers
function center = initCenter(clusterNum, dataSet)
% ====== Method 1: Randomly pick clusterNum data points as cluster centers
%dataNum = size(dataSet, 1);
%tmp = randperm(dataNum);
%index = tmp(1:clusterNum);
%center = dataSet(index, :);
% ====== Method 2: Choose clusterNum data points closest to the mean vector
meanVec = mean(dataSet);
dist = vecdist(meanVec, dataSet);
[a,b] = sort(dist);
center = dataSet(b(1:clusterNum), :);
% ====== Method 3: Choose clusterNum data points furthest to the mean vector
%meanVec = mean(dataSet);
%dist = vecdist(meanVec, dataSet);
%[a,b] = sort(dist);
%b = fliplr(b);
%center = dataSet(b(1:clusterNum), :);


% ====== Find new centers
function [center, distortion, U] = updateCenter(center, dataSet)
centerNum = size(center, 1);
dataNum = size(dataSet, 1);
dim = size(dataSet, 2);
% ====== Find the U (partition matrix)
dist = vecdist(center, dataSet);		% fill the distance matrix
[a,b] = min(dist);
index = b+centerNum*(0:dataNum-1);
U = zeros(size(dist));
U(index) = ones(size(index));
% ====== Check if there is an empty group (and delete them)
index=find(sum(U,2)==0);
emptyGroupNum=length(index);
if emptyGroupNum~=0,
	warning('Found empty group(s)!');
	U(index,:)=[];
end
% ====== Find the new centers
center = (U*dataSet)./(sum(U,2)*ones(1,dim));
% ====== Add new centers for the deleted group
if emptyGroupNum~=0,
	center=[center; center(1:emptyGroupNum,:)+eps];
end
% ====== Find the new objective function
dist = vecdist(center, dataSet);			% fill the distance matrix
distortion = sum(sum((dist.^2).*U));		% objective function


% ====== Self demo
function selfdemo
dataNum = 150;
data1 = ones(dataNum, 1)*[0 0] + randn(dataNum, 2)/5;
data2 = ones(dataNum, 1)*[0 1] + randn(dataNum, 2)/5;
data3 = ones(dataNum, 1)*[1 0] + randn(dataNum, 2)/5;
data4 = ones(dataNum, 1)*[1 1] + randn(dataNum, 2)/5;
dataSet = [data1; data2; data3; data4];
centerNum=8;
plotOpt=1;
[center, U, distortion] = feval(mfilename, dataSet, centerNum, plotOpt);