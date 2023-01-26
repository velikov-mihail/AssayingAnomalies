function plotNameHistogram(x, labels)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It plots a name histogram similar to the one used in Figure A.5. 
%------------------------------------------------------------------------------------------
% USAGE:   
% plotNameHistogram(x, labels)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        - x - statistics used for the histogram plot
%        - labels - labels for each data point plotted on the name histogram
%------------------------------------------------------------------------------------------
% Output:
%        - N/A
%------------------------------------------------------------------------------------------
% Examples:
%
% plotNameHistogram(x, labels)
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

% We'll do bins by 20 percentage points
xLims = ceil(max(abs(x)/20))*20;
bins = (-xLims):20:(xLims);

% Store a few constants
nBins = length(bins);
strLim = 10;
fontSize = 7;

% Remove underscores & limit to strLim 
labels = regexprep(labels, '_', '');
labels = cellfun(@(x) extractBetween(x, 1, min(strLim,length(x))), labels);

% Store the number of data points per bin
nCountsPerBin = histcounts(x, bins);

% Loop through the bins
for i = 1:nBins-1

    % If more than one data point in this bin
    if nCountsPerBin(i)>0    
        % Find the data in this bin
        pointsInBin = (x >= bins(i) & ...
                       x <  bins(i+1));

        % Sort alphabetically 
        [srtdLabels, ~] = sort(labels(pointsInBin));    
        
        for j=1:nCountsPerBin(i)          
            % Add this data point to the histogram
            text(i, ...
                 j, ...
                 srtdLabels{j},...
                 'color', 'black',...
                 'fontsize', fontSize,...
                 'fontangle', 'normal',...
                 'fontweight', 'normal',...
                 'interpreter', 'latex');    
        end    
    end
end

h = get(gca);
ymax = ceil((max(nCountsPerBin))/10)*10;
ylim([0 ymax])
xlim([0.8 nBins+.2]);  
xticks(1:nBins);
h.XAxis.TickLabel = bins(1:end);
set(gcf,'position', [      965   200   988   707])