function ind = assignToPtf(x, bPtsMat)
% PURPOSE: Function that assigns each firm-month to the bin it belongs to in the
% particular month. It assigns a zero if a firm-month is not held in any
% portfolio.
%------------------------------------------------------------------------------------------
% USAGE: 
% index = assign(x, bPtsMat)
%------------------------------------------------------------------------------------------
% Inputs
%        -x -matrix based on which we want to assign the bins 
%        -bPtsMat -a matrix with the breakpoints (values) for each time period
% Output
%        -ind -a matrix that indicates the bin each stock-time is in
%------------------------------------------------------------------------------------------
% Examples:
%
% ind = assignToPtf(me, prctile(me,[20 40 60 80],2)) % Quintile sort on size
%------------------------------------------------------------------------------------------
% Dependencies:
%       Uses N/A
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% Store several dimensions
nStocks = size(x, 2);
nPeriods = size(x, 1);
nBPoints = size(bPtsMat, 2);

% Create a matrix with the same dimensions as x
ind = zeros(nPeriods, nStocks);                        

% Assign the indicator for the first portfolio
bPtsPtfOne = bPtsMat(:,1);                                
rptdBPtsPtfOne = repmat(bPtsPtfOne, 1, nStocks);                 
ind(x < rptdBPtsPtfOne) = 1;                            

% Repeat the same for all the other breakpoints 
for j = 1:nBPoints
    bPtsPtfJ = bPtsMat(:,j);
    rptdBPtsPtfJ = repmat(bPtsPtfJ, 1, nStocks);                 
    ind(x >= rptdBPtsPtfJ) = j+1;
end





