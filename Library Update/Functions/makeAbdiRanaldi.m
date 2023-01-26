function chl = makeAbdiRanaldi()
% PURPOSE: This function creates the Abdi and Ranaldo (RFS, 2017) effective
% spread estimate as used in Chen and Velikov (JFQA, 2021)
%------------------------------------------------------------------------------------------
% USAGE:   
% chl = makeAbdiRanaldi()              
%------------------------------------------------------------------------------------------
% Required Inputs:
%        - N/A
%------------------------------------------------------------------------------------------
% Output:
%        -chl - a matrix with the effective spread estimates 
%------------------------------------------------------------------------------------------
% Examples:
%
% chl = makeAbdiRanaldi()              
%------------------------------------------------------------------------------------------
% Dependencies:
%       N/A
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Abdi, F. and A. Ranaldo, 2017, A simple estimation of bid-ask spreads
%  from daily close, high, and low prices, Review of Financial Studies, 30
%  (12): 4437-4480
%  2. Chen, A. and M. Velikov, 2021, Zeroing in on the expected return on 
%  anomalies, Journal of Financial and Quantitative Analysis, Forthcoming.
%  3. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% Timekeeping
fprintf('Now working on Abdi and Ranaldo CHL effective spread construction. Run started at %s.\n', char(datetime('now')));

% Load the necessary variables
load dbidlo
load daskhi
dhigh=dbidlo;
dlow=daskhi;
clear dbidlo daskhi
load dprc
load ddates
load dates
load ret

% Store the number of days and number of months
nDays = length(ddates);
nMonths = length(dates);

% Store the raw daily price matrix
dprc_raw = dprc;

% Set the daily high and low for days when a stock does not trade to nan
dhigh(dprc<0 | isnan(dprc)) = nan;
dlow(dprc<0 | isnan(dprc)) = nan;

% Carry over the previous days daily high, low, and close on days when a
% stock doesn't trade (see bottom of pg. 4454)
for i=2:nDays
    % Adjust daily closing price
    ind = isnan(dprc(i,:)) & isfinite(dprc(i-1,:));
    dprc(i,ind) = dprc(i-1,ind);
    
    % Adjust daily high
    ind = isnan(dhigh(i,:)) & isfinite(dhigh(i-1,:));
    dhigh(i,ind) = dhigh(i-1,ind);
    
    % Adjust daily low
    ind = isnan(dlow(i,:)) & isfinite(dlow(i-1,:));
    dlow(i,ind) = dlow(i-1,ind);    
end

% Take the absolute value of the daily price (CRSP has negative prices on
% days the stock doesn't trade)
dprc = abs(dprc);

% Find the first month
s = find(dates==floor(ddates(1)/100));

% Store the midpoints of the low and high for t and tp1 (= t plus one)
midpoint = (log(dlow) + log(dhigh)) / 2;
midpoint_tp1 = lead(midpoint, 1, nan);

% Clear dhigh and dlow as we only need them to calculate the midpoint
clear dhigh dlow

% Re-load the low and high 
load dbidlo
load daskhi

% set the days where the stock does not trade to nan
dbidlo(dprc_raw<0 | isnan(dprc_raw)) = nan;
daskhi(dprc_raw<0 | isnan(dprc_raw)) = nan;

% Initiate the close-high-low effective spread measure
chl = nan(size(ret));

% Loop over the months
for i = s:nMonths
    
    % Find the days in this month
    month_ind = find(floor(ddates/100)==dates(i));
    
    % Find the stocks that have 12 applicable days (see top of pg. 4455)
    hor_ind = find(sum( dprc_raw(month_ind,:)>0         & ...
                        isfinite(dprc_raw(month_ind,:)) & ...
                        isfinite(dbidlo(month_ind,:))   & ...
                        isfinite(daskhi(month_ind,:))   & ...
                        daskhi(month_ind,:)-dbidlo(month_ind,:)~=0 ...
                        , 1) >= 12);
                      
    % store the two eta's and c to be used in equation 11
    eta_tp1 = midpoint_tp1(month_ind, hor_ind);
    eta_t   = midpoint(month_ind, hor_ind);
    c_t     = log(dprc(month_ind, hor_ind));
    
    % Calculate the spread following equation 11
    s_hat_t = sqrt( max( 4 * (c_t-eta_t) .* (c_t-eta_tp1) ,0) );
    chl(i, hor_ind) = mean(s_hat_t,1,'omitnan');
end
