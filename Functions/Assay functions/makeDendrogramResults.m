function [Z, dendrogramLabels, cutoff] = makeDendrogramResults(resAnoms, signalLabel, labels, resBasicSorts, timePeriod)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It creates results for an aggolmerative hierarchical cluster plot
% using Ward's minimum method and a maximum of 10 clusters. 
%------------------------------------------------------------------------------------------
% USAGE:   
% [Z, dendrogramLabels, cutoff] = makeDendrogramResults(resAnoms,labels,resBasicSorts,timePeriod)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        - resAnoms - vector (nAnoms x 1) of structures containing the
%                     univariate sort results
%        - resBasicSorts - vector (nAnoms x 1) of structures with univariate
%                          sort results
%        - labels - a structure with two cell arrays that contain strings 
%                   with short and long label for each anomaly
%        - timePeriod - 1x2 vector with start and end dates in YYYYMM
%                       format
%------------------------------------------------------------------------------------------
% Output:
%        - Z - matrix Z that encodes a tree containing hierarchical clusters
%        - dendrogramLabels - the labels used in the dedrogram plot
%        - cutoff - threshold for unique colors in the dendrogram plot
%------------------------------------------------------------------------------------------
% Examples:
%
% [Z, dendrogramLabels, cutoff] = makeDendrogramResults(resAnoms,labels,resBasicSorts,timePeriod)
%------------------------------------------------------------------------------------------
% Dependencies:
%       N/A
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% Timekeeping
fprintf('\nNow working on making dendrogram data. Run started at %s.\n', char(datetime('now')));

% Load the dates vector & figure out the sample
load dates
s = find(dates==timePeriod(1));
e = find(dates==timePeriod(2));

% Store a few variables
nAnoms = length(resAnoms);
nMonths = length(dates);

% Store the anomaly portfolio returns
anomRets = nan(nMonths, nAnoms);
for i=1:nAnoms
    if ~isempty(resAnoms(i).xret)
        anomRets(s:e, i) = resAnoms(i).pret(s:e,end);
    end
end

% Store the signal portfolio returns
signalRet = nan(nMonths, 1);
signalRet(s:e) = resBasicSorts(1,1).res.pret(s:e,end);

% Combine the anoms
rets = [anomRets(s+1:e, :) signalRet(s+1:e)];
dendrogramLabels = [labels {['\color{red}{', char(signalLabel),'}']}];

% Drop anoms with shorter samples
anomsToKeep = isfinite(sum(rets, 1));
rets = rets(:, anomsToKeep);
dendrogramLabels = dendrogramLabels(anomsToKeep);

% Run the dendrogram analysis
Z = linkage(rets', 'ward');

% Color threshold cutoff
cutoff = prctile([Z(:,3)], 75);

% % Plot the figure
% figure('Visible','on');
% dendrogram(Z, nAnoms, 'Labels', dendrogramLabels, ...
%                          'ColorThreshold', cutoff);
% xtickangle(90)
% set(gca, 'FontSize', 8, ...
%          'LooseInset',get(gca,'TightInset'));
% set(gcf, 'PaperPositionMode', 'auto', ...
%          'units','normalized','outerposition',[0 0 1 1]);

% Timekeeping
fprintf('\nDone with making dendrogram data at %s.\n\n', char(datetime('now')));
