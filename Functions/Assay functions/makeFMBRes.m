function eret = makeFMBRes(filledAnoms, dates, timePeriod, ret)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It calculates the forecast return combination signals using 
% Fama-MacBeth regressions as the method and runs univariate sorts.
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
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% Timekeeping
fprintf('\nNow working on Fama-MacBeth with %d anomales. Run started at %s.\n', ...
                               size(filledAnoms, 3), char(datetime('now')));

% Turn off warnings
warning('off','all')

% Start and end dates
s = find(dates==timePeriod(1));
e = find(dates==timePeriod(2));

% Subset
filledAnoms = filledAnoms(s:e, :, :);
ret = ret(s:e, :);

% Determine the rolling period
[nMonths, nStocks, nAnoms] = size(filledAnoms);
T = 120;
temp_eret = nan(size(ret));

% Initialize the beta matrix and ta constant
betas = nan(nMonths, nAnoms);
const = ones(nStocks, 1);

% Loop through the months
for i = 2:nMonths
    if mod(i,T)==0
        fprintf('Done until %d @ %s.\n', dates(s+i-1), char(datetime('now')));
    end
    
    % Estimate this month's betas
    lagX = permute(filledAnoms(i-1, :, :), [2 3 1]);

    % Figure out which anomalies we are using
    numObsPerAnom = sum(isfinite(lagX) & lagX~=0, 1, 'omitnan');
    anomsToUse = find(numObsPerAnom > 0);    

    % Assign to y and x and winsorize
    y = ret(i, :)';
    x = winsorize(lagX(:, anomsToUse)', 1)';   

    % If any pair of anomalies have >90% correlation, drop one
    corrs = tril(corrcoef(x(sum(isnan(x), 2) == 0, :)));
    corrs(logical(eye(size(corrs, 1)))) = 0;
    indToRemove = any(abs(corrs)>0.90);
    anomsToUse(indToRemove) = [];

    % Redefine x
    x = [const winsorize(lagX(:, anomsToUse)', 1)'];   
    
    % Regress 
    bhat = regress(y, x);
    betas(i, anomsToUse) = bhat(2:end);
    
    % Calculate fitted values
    if i >= T
        bMean = mean(betas(i-T+1:i, :), 1, 'omitnan');
        indToUse = isfinite(bMean);
        thisMonthX = permute(filledAnoms(i, :, indToUse), [2 3 1]);
        temp_eret(i,:) = (thisMonthX * bMean(indToUse)')';               
    end
end

% Assign it to the output
eret = nan(length(dates), nStocks);
eret(s:e, :) = temp_eret;

% Timekeeping
fprintf('Done with Fama-MacBeth at %s.\n',char(datetime('now')));