function eret = makeLassoRes(filledAnoms, ret, dates, timePeriod)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It calculates the forecast return combination signals using 
% LASSO as the method and runs univariate sorts.
%------------------------------------------------------------------------------------------
% USAGE:   
% eret = makeLassoRes(filledAnoms, ret, dates, timePeriod)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        - filledAnoms - 3-d numeric array (nMonths x nStocks x nAnoms) 
%                        with filled-in anomaly signals
%        - ret - numeric matrix (nMonths x nStocks) with monthly returns
%        - dates - numeric vector (nMonths x 1) of dates in YYYYMM format
%        - timePeriod - 1x2 vector with start and end dates in YYYYMM
%                       format
%------------------------------------------------------------------------------------------
% Output:
%        - eret - numeric matrix (nMonths x nStocks) with forecast returns
%------------------------------------------------------------------------------------------
% Examples:
%
% eret = makeLassoRes(filledAnoms, ret, dates, timePeriod);
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
fprintf('\nNow working on LASSO with %d anomales. Run started at %s.\n', ...
                               size(filledAnoms, 3), char(datetime('now')));

% Sample start and end dates
s = find(dates==timePeriod(1));
e = find(dates==timePeriod(2));

% Store some dimensions & some constants
[nMonths, nStocks, nAnoms] = size(filledAnoms);
nAnomMonths = e-s+1;
T = 120;
nObs = nAnomMonths * nStocks;

% Reshape the dates, returns and anomaly variables
lassoDates = reshape(repmat(dates(s:e), 1 ,nStocks), nObs, 1);
lassoY = reshape(ret(s:e,:), nObs, 1);
lassoX = nan(nObs, nAnoms);
for i = 1:nAnoms
    % Important to lag them here
    laggedAnom = filledAnoms(s-1:e-1, :, i);
    lassoX(:, i) = reshape(laggedAnom, nObs, 1);
end 

% Filter the ones for which we have data
indToLeave = isfinite(lassoY) & sum(isfinite(lassoX),2)>0;
lassoY = lassoY(indToLeave);
lassoX = lassoX(indToLeave, :);
lassoDates = lassoDates(indToLeave);

% Initialize the beta and forecast return matrices
bhat = nan(nMonths, nAnoms);
eret = nan(nMonths, nStocks);

% Loop through the months
for i = (s+T):e
    if mod(i,T)==0
        fprintf('Done until %d @ %s.\n', dates(i), char(datetime('now')));
    end
    
    % Choose the sample - past T months 
    ind = lassoDates >= dates(i-T+1) & ...
          lassoDates <= dates(i);
    
    % Subset y and x
    y = lassoY(ind);
    x = lassoX(ind, :);
    
    % Find the ones for which we don't have missing observations
    sumX = sum(abs(x), 1);
    ind = find(~isnan(sumX) & ...
                sumX~=0);

    % Run the LASSO with 5-fold cross-validation
    [B, fitInfo] = lasso(x(:, ind), y, 'CV', 5);
    
    % Find the minimum MSE & use those coefficients to forecast the return.
    minMSE = find(fitInfo.MSE==min(fitInfo.MSE), 1);
    eret(i,:) = (permute(filledAnoms(i, :, ind), [2 3 1]) * B(:,minMSE))';
    bhat(i, ind) = B(:,minMSE)';        
end

% Timekeeping
fprintf('Done with LASSO at %s.\n',char(datetime('now')));