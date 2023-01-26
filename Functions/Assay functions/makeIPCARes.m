function eret = makeIPCARes(filledAnoms, keepRollAnoms, ret, rf, dates, timePeriod)
% PURPOSE: This function is part of the protocol of tests for proposed new
% cross-sectional anomaly signals established in Novy-Marx and Velikov
% (2023). It calculates the forecast return combination signals using 
% Instrumented Principal Components from Kelly, Pruitt, and Su (2019)
% as the method and runs univariate sorts.
%------------------------------------------------------------------------------------------
% USAGE:   
% eret = makeIPCARes(filledAnoms, keepRollAnoms, ret, rf, dates, timePeriod)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        - filledAnoms - 3-d numeric array (nMonths x nStocks x nAnoms) 
%                        with filled-in anomaly signals
%        - keepRollAnoms - matrix (nMonths x nAnoms) indicating whether an
%                          anomaly has had more than 40% of market cap
%                          observations in the average month over the past
%                          10 years.
%        - ret - numeric matrix (nMonths x nStocks) with monthly returns
%        - rf - numeric vector (nMonths x 1) with risk-free rate monthly
%               returns               
%        - dates - numeric vector (nMonths x 1) of dates in YYYYMM format
%        - timePeriod - 1x2 vector with start and end dates in YYYYMM
%                       format
%------------------------------------------------------------------------------------------
% Output:
%        - eret - numeric matrix (nMonths x nStocks) with forecast returns
%------------------------------------------------------------------------------------------
% Examples:
%
% eret = makeIPCARes(filledAnoms, keepRollAnoms, ret, rf, dates, timePeriod);
%------------------------------------------------------------------------------------------
% Dependencies:
%       Uses runIPCAforMonth()
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Kelly, B., Pruitt, S., and Y. Su, 2019, Characteristics are
%  covariances: A unified model of risk and return, Journal of Financial
%  Economics, 134 (3): 501-524
%  2. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% Timekeeping
fprintf('\nNow working on IPCA with %d anomales. Run started at %s.\n', ...
                               size(filledAnoms, 3), char(datetime('now')));


% Store the dimensions
[nMonths, nStocks, ~] = size(filledAnoms);
T = 120;

% Sample start and end date
b = find(dates == timePeriod(1));
e = find(dates == timePeriod(2));


% Initiate the output
eret = nan(nMonths, nStocks);

% Get the excess returns
xret = (ret - repmat(rf, 1, nStocks));

% loop through the months
for i = b+T+1:e-1
    if mod(i,T)==0
        fprintf('Done until %d @ %s.\n',dates(i),char(datetime('now')));
    end    


    if sum(keepRollAnoms(i-1,:)) > 0
        % Lag the anoms we pass to runIPCAforMonth here
        thisAnoms = filledAnoms(i-T:i-1,:, keepRollAnoms(i-1,:)==1);
        thisXret = xret(i-T+1:i, :)';
    
        % Run the IPCA for this month
        [GammaBeta,  Lambda] = runIPCAforMonth(thisAnoms, thisXret); 
        
        % Calculate the forecast return
        nextMonthAnoms = permute(filledAnoms(i, :, keepRollAnoms(i-1,:) == 1), [3 2 1]);
        nextMonthAnoms(size(nextMonthAnoms, 1)+1, :) = 1; % Add a constant
        eret(i, :) = (nextMonthAnoms' * GammaBeta * Lambda)';
    end
end

% Timekeeping
fprintf('Done with IPCA calculation at %s.\n',char(datetime('now')));
