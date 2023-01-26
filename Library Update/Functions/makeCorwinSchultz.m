function hl = makeCorwinSchultz()
% PURPOSE: This function creates the Corwin and Schultz (JF, 2012) 
% effective spread estimate as used in Chen and Velikov (JFQA, 2021)
%------------------------------------------------------------------------------------------
% USAGE:   
% hl = makeCorwinSchultz()              
%------------------------------------------------------------------------------------------
% Required Inputs:
%        - N/A
%------------------------------------------------------------------------------------------
% Output:
%        -hl - a matrix with the effective spread estimates 
%------------------------------------------------------------------------------------------
% Examples:
%
% hl = makeCorwinSchultz()              
%------------------------------------------------------------------------------------------
% Dependencies:
%       N/A
%------------------------------------------------------------------------------------------
% Copyright (c) 2022 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Chen, A. and M. Velikov, 2021, Zeroing in on the expected return on 
%  anomalies, Journal of Financial and Quantitative Analysis, Forthcoming.
%  2. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.
%  3. Corwin, S. and P. Schultz, 2012, A simple way to estimate bid-ask
%  spreads from daily high and low prices, Journal of Finance, 67 (2):
%  719-760

% Timekeeping
fprintf('Now working on Corwin and Schultz HL effective spread construction. Run started at %s.\n', char(datetime('now')));

% Load the necessary variables
load dbidlo
load daskhi
load ddates
load dprc
load ret
load dates
load dcfacpr


%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Section II.A
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
hi = daskhi;
lo = dbidlo;

hi(dprc<0) = nan;
lo(dprc<0) = nan;

dprc = abs(dprc);
lclose = lag(dprc,1,nan) .* dcfacpr ./ lag(dcfacpr,1,nan);


% Page 726: "If the day t+1 low is above the day t close, we assume that the price rose
% overnight from the close to the day t+1 low and decrease both the high and low
% for day t+1 by the amount of the overnight change when calculating spreads.
% Similarly, if the day t+1 high is below the day t close, we assume the price fell
% overnight from the close to the day t+1 high and increase the day t+1 high and
% low prices by the amount of this overnight decrease."
pchg = zeros(size(dprc));
pchg(dbidlo > lclose) = dbidlo(dbidlo > lclose) - lclose(dbidlo > lclose);
pchg(daskhi < lclose) = daskhi(daskhi < lclose) - lclose(daskhi < lclose);
lo = lo - pchg;
hi = hi - pchg;
clear pchg lclose daskhi dbidlo

lhi = lag(hi,1,nan) .* dcfacpr ./ lag(dcfacpr,1,nan);
llo = lag(lo,1,nan) .* dcfacpr ./ lag(dcfacpr,1,nan);

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Actual spread estimation
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Equation (7):
beta = (log(hi./lo)).^2 + (log(lhi./llo)).^2; 
beta(hi<=0 | lo<=0) = nan;

% Equation (10):
gamma = (log(max(hi,lhi) ./ min(lo,llo))) .^ 2; 
gamma(min(lo,llo)<=0)=nan;
clear lo hi ldlow ldhigh dprc llo lhi

% Define the constatn
const = 3 - 2*sqrt(2);

% Equation (18):
alpha = (sqrt(2*beta) - sqrt(beta)) / const - ...   
         sqrt(gamma/const);

% Equation (14)
s = 2*(exp(alpha)-1) ./ (1+exp(alpha)); 

%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Section II.C
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%
% Page 727: "The high–low estimator assumes that the expectation of a stock’s true variance over a 2-day period is twice as large as the expectation of the variance over
% a single day. Even if this is true in expectation, the observed 2-day variance may be more than twice as large as the single-day variance during volatile
% periods, in cases with a large overnight price change, or when the total return over the 2-day period is large relative to the intraday volatility. If the observed
% 2-day variance is large enough, the high–low spread estimate will be negative. For most of the analysis to follow, we set all negative 2-day spreads to zero
% before calculating monthly averages."
s(s < 0) = 0;

% Initialize the high-low spread measure and store the number of months
hl = nan(size(ret));
nMonths = length(dates);

% Loop through the months
for i=1:nMonths
    ind = find(floor(ddates/100)==dates(i));
    hor_index = sum(isfinite(s(ind,:)),1) >= 12;
    hl(i,hor_index) = nanmean(s(ind,hor_index),1);
end

% Get rid of any imaginary numbers
hl = real(hl);

