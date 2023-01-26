function indOut = make_sS(indIn, sSThresholds, indInMargin)
% PURPOSE: Creates a buy/hold indicator
%------------------------------------------------------------------------------------------
% USAGE: indOut = make_sS(indin, sSThresholds, indInMargin);
%------------------------------------------------------------------------------------------
% Inputs:
%        -indIn - an index matrix specifying the portfolio before banding
%        -sSThresholds - Number of portfolios to buy
%        -indInMargin - an index matrix, specifying the portfolio ...
% Output:
%        -indOut - an index matrix specifying the portfolio after banding 
%------------------------------------------------------------------------------------------
% Examples:
%
% indOut = make_sS(indIn, Nprts); make sS holding top Nprts
% indOut = make_sS(indIn, Nprts, indInMargin); delays sales (short covers) on the margin if indInMargin looks good (bad)
%   can also be used to make an sS strategy using a second indicator to determine the s boundary  
% indOut = make_sS(indIn, [Nprt1 Nprt2], indInMargin); trades indInMargin on the boundary of indin trades
%   accelerates buys if in top Nprt1 of indin and in top Nprt2 of indin2
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


% Assign the output index
indOut = indIn; 

% Store the total number of portfolios & number of months
nPtfs = max(max(indIn));

% Figure out if we are doing trading on the margin
if nargin == 3
    tempIndMargin = indInMargin; 
    N2 = max(max(tempIndMargin));
else
    tempIndMargin = indOut; 
    N2 = nPtfs;
end

% Determine the buy/hold thresholds
M = max(size(sSThresholds));
if M == 1
    Nprt1 = 0;
    Nprt2 = sSThresholds;
else % this delays sales (short covers) on the margin
    Nprt1 = sSThresholds(1);
    Nprt2 = sSThresholds(2);
end

% Loop through the months with data
indFin = find(sum(indOut,2)>0);
nMonthsWithData = length(indFin);
for i = 2:nMonthsWithData
    
    % Slows sales/speeds purchases
    horInd = (indOut(indFin(i-1),:)     >= nPtfs - Nprt1    & ...
              tempIndMargin(indFin(i),:) >= N2 + 1 - Nprt2   );
    indOut(indFin(i), horInd == 1) = nPtfs; 
    
    % Slows short covers / speeds shorting
    horInd = (indOut(indFin(i-1),:) <= 1 + Nprt1 & ...
              indOut(indFin(i-1),:) > 0          & ...
              tempIndMargin(indFin(i),:) <= Nprt2 & ...
              tempIndMargin(indFin(i),:) > 0      );
    indOut(indFin(i),horInd == 1) = 1; 
        
    % Slows buys
    horInd = (indOut(indFin(i-1),:) < nPtfs      & ...
              indOut(indFin(i),:) == nPtfs       & ...
              tempIndMargin(indFin(i),:) <= Nprt2 & ...
              tempIndMargin(indFin(i),:) > 0      );
    indOut(indFin(i),horInd == 1) = nPtfs-1; 
    
    % Slows shorting
    horInd = (indOut(indFin(i-1),:) > 1                   & ...
              indOut(indFin(i),:) == 1                    & ...
              tempIndMargin(indFin(i),:) >= N2 + 1 - Nprt2 );
    indOut(indFin(i),horInd == 1) = 2; 
        
end
