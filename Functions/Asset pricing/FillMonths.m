function filledData = FillMonths(data, persist)
% PURPOSE: Fills in data for matrices with less granular data than the one
% indicated in the dates/ddates vector
%------------------------------------------------------------------------------------------
% USAGE: filledData = FillMonths(data, persist);
%------------------------------------------------------------------------------------------
% Inputs:
%        -data - a matrix of data, usually a signal that changes annually                          
%        -persist - level of persistence 
% Output:
%        -filledData - matrix of data, where usually annual values are filled
%                   in for every month
%------------------------------------------------------------------------------------------
% Examples:
%
% load bm
% filledBM = FillMonths(bm);
%                           
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

% Initialize the output matrix
filledData = data;

% Store total number of dates
nDates = size(data, 1);

% Find the months with data & figure out the frequency
indRowsWithData = find(sum(isfinite(data),2) > 0);
nRowsWithData = length(indRowsWithData);
dataFreq = mode(indRowsWithData-lag(indRowsWithData, 1, nan));

% If annual
if dataFreq == 12
    for i = 1:nRowsWithData
        thisRow = indRowsWithData(i);
        b = thisRow + 1;
        e = min(thisRow+11, nDates);
        
        nRep = e-b+1;
        if nRep>0
            filledData(b:e, :) = repmat(data(thisRow, :), nRep, 1);
        end
    end
else
    % Assume quarterly and loop through columns
    if nargin == 1
        persist = 2;
    end

    % Find all the columns with data
    indColsWithData = find(sum(isfinite(data), 1) > 0);
    nColsWithData = length(indColsWithData);

    % Loop through them & fill them in
    for i = 1:nColsWithData
        thisCol = indColsWithData(i);
        thisColDataIsFinite = isfinite(filledData(:,thisCol));
        
        % Fill them in 
        mm = find(thisColDataIsFinite, 1, 'first');
        MM = find(thisColDataIsFinite, 1, 'last');
        for j = mm+1:min(nDates,MM+persist)
            if isnan(filledData(j,thisCol))
                filledData(j,thisCol) = filledData(j-1,thisCol);
            end
        end
    end
end

