function eret = makeWeightedAverageRank(filledAnoms, pret, me, dates, timePeriod) 
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It calculates the forecast return combination signals using 
% weighted-average rank as the method and runs univariate sorts.
%------------------------------------------------------------------------------------------
% USAGE:   
% eret = makeWeightedAverageRank(filledAnoms,me) 
%------------------------------------------------------------------------------------------
% Required Inputs:
%        - filledAnoms - 3-d numeric array (nMonths x nStocks x nAnoms) 
%                        with filled-in anomaly signals
%        - pret - numeric matrix (nMonths x nAnoms) of anomaly portfolio
%                 returns
%        - me - numeric matrix (nMonths x nStocks) with market
%               capitalization
%        - dates - numeric vector (nMonths x 1) of dates in YYYYMM format
%        - timePeriod - 1x2 vector with start and end dates in YYYYMM
%                       format
%------------------------------------------------------------------------------------------
% Output:
%        - eret - numeric matrix (nMonths x nStocks) with forecast returns
%------------------------------------------------------------------------------------------
% Examples:
%
% eret = makeWeightedAverageRank(filledAnoms,me);
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
fprintf('\nNow working on weighted-average rank with %d anomales. Run started at %s.\n', ...
                               size(filledAnoms, 3), char(datetime('now')));

% Determine start and end dates
s = find(dates==timePeriod(1));
e = find(dates==timePeriod(2));

% Initialize the forecast return matrix
eret = nan(size(me));

% Set the lookback period
lbp = 120;

% Loop over the months
for i = s+lbp:e
    % Calculate the weights
    weights = mean(pret(i-lbp+1:i, :), 1)';
    weights(weights<0) = 0;
    weights = weights / sum(weights, 'omitnan');
    
    % Calculate the forecast return
    ind = find(isfinite(weights));
    eret(i,:) = (permute(filledAnoms(i, :, ind),[2 3 1]) * weights(ind))';    
end


% Timekeeping
fprintf('Done with weighted-average rank at %s.\n',char(datetime('now')));