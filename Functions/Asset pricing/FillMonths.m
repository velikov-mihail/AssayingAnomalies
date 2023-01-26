function filledData = FillMonths(data,persist)
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
% filledBM = FillMonths(bm);
%                           
%------------------------------------------------------------------------------------------
% Dependencies:
%       N/A
%------------------------------------------------------------------------------------------
% Copyright (c) 2022 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2022, Assaying anomalies, Working paper.

filledData = data;

% Find the months with data & figure out the frequency
indRowsWithData = find(sum(isfinite(data),2) > 0);
nRowsWithData = length(indRowsWithData);
dataFreq = mode(indRowsWithData-lag(indRowsWithData, 1, nan));

% If annual
if dataFreq == 12
    for i = 1:nRowsWithData
        thisRow = indRowsWithData(i);
        
        for j = 1:11
            if thisRow+j <= rows(data)
                filledData(thisRow+j,:) = data(thisRow,:);
            end
        end
    end
% Assume quarterly    
else
    if nargin == 1
        persist = 2;
    end
    indexh = sum(isfinite(filledData)) > 0;
    index1 = find(indexh == 1);
    for i = 1:cols(index1)
        c = index1(i);
        indexv = isfinite(filledData(:,c));
        mm = min(find(indexv == 1));
        MM = max(find(indexv == 1));
        for j = mm+1:min(rows(filledData),MM+persist)
            if isfinite(filledData(j,c)) == 0
                filledData(j,c) = filledData(j-1,c);
            end
        end
    end
end

