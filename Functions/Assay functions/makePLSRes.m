function eret = makePLSRes(filledAnoms, dates, timePeriod, ret)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It calculates the forecast return combination signals using 
% the Partial Least Squares (PLS) from Light, Masov, and Rytchkov (201() as 
% the method and runs univariate sorts.
%------------------------------------------------------------------------------------------
% USAGE:   
% eret = makeFMBRes(filledAnoms, dates, timePeriod, ret)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        - filledAnoms - 3-d numeric array (nMonths x nStocks x nAnoms) 
%                        with filled-in anomaly signals
%        - dates - numeric vector (nMonths x 1) of dates in YYYYMM format
%        - timePeriod - 1x2 vector with start and end dates in YYYYMM
%                       format
%        - ret - numeric matrix (nMonths x nStocks) with monthly returns
%------------------------------------------------------------------------------------------
% Output:
%        - eret - numeric matrix (nMonths x nStocks) with forecast returns
%------------------------------------------------------------------------------------------
% Examples:
%
% eret = makeFMBRes(filledAnoms, dates, timePeriod, ret);
%------------------------------------------------------------------------------------------
% Dependencies:
%       N/A
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Light, N., Maslov D., and O. Rytchkov, 2017, Aggregation of
%  information about the cross section of stock returns: A latent variable
%  approach, Review of Financial Studies, 30, 1339-1381
%  2. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% Timekeeping
fprintf('\nNow working on Partial Least Squares with %d anomales. Run started at %s.\n', ...
                               size(filledAnoms, 3), char(datetime('now')));

% Sample start and end date
s = find(dates==timePeriod(1));
e = find(dates==timePeriod(2));

% Store some dimensions
[nMonths, nStocks, nAnoms] = size(filledAnoms);

% Initialize the forecast return and lambda matrices
eret = nan(nMonths, nStocks);
lambda = nan(nMonths, nAnoms);

% Loop through the months
for i = s:e
    if mod(i,120)==0
        fprintf('Done until %d @ %s.\n', dates(i), char(datetime('now')));
    end
    
    y = ret(i,:)';
    x = permute(filledAnoms(i-1, :, :), [2 3 1]);
    xt = permute(filledAnoms(i, :, :), [2 3 1]);
    
    % Step 1
    for j = 1:nAnoms
        res = nanols(y, x(:, j));
        lambda(i,j) = res.beta;
    end
    
    % Step 2
    for j = 1:nStocks
        res = nanols(xt(j,:)', lambda(i, :)');
        eret(i, j) = res.beta;
    end
end

% Timekeeping
fprintf('Done with PLS at %s.\n',char(datetime('now')));