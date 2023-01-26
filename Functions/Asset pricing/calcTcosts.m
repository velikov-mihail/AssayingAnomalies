function [ptfTC, ptfTO, dW] = calcTcosts(tcosts, ind, me, varargin)
% PURPOSE: creates trading costs, turnover, and weight change matrix for a
% given asset pricing factor
%---------------------------------------------------
% USAGE: [fTC, ptfTO, dW] = makeFactorTcosts(tcosts, me, w, ind)     
%                      Assumes a constant base of $1 for the factor trading
%                      strategy
%        [fTC, ptfTO, dW] = makeFactorTcosts(tcosts, me, w, ind, pret)
%                      Allows for increasing the base of the factor trading
%                      strategy by (1+r) each month using pret
%---------------------------------------------------
% Inputs
%        -tcosts - matrix with effective spread trading costs 
%        -me - matrix with market capitalizations
%        -w - matrix with weights of individual stocks 
%        -ind - index indicating whether a stock is held in a short (=1)
%                or long (=2) position
%        -pret - return time-series for long and short portfolio 
% Outputs
%        -fTC - time series of factor trading costs
%        -ptfTO - time series of factor's portfolios turnover
%        -dW - matrix with changes in individual stock weights
%------------------------------------------------------------------------------------------
% Examples:
%
% [smb_tc, smb_TO, ~] = makeFactorTcosts(tcosts, me, wFF93/3, indSMB);
%------------------------------------------------------------------------------------------
% Dependencies:
%       Used by makeFFTcosts()
%------------------------------------------------------------------------------------------
% Copyright (c) 2022 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Detzel, A., Novy-Marx, R., and M. Velikov, 2022, Model Comparison 
%  with Trading Costs, Working paper.
%  2. Novy-Marx, R. and M. Velikov, 2022, Assaying anomalies, Working paper.

% Parse the inputs
p = inputParser;

% Define the validating functions
validNum = @(x) isnumeric(x);

% Add the required 
addRequired(p, 'tcosts', validNum);
addRequired(p, 'ind',    validNum);
addRequired(p, 'me',     validNum);

% Add the optional inputs
addOptional(p, 'weighting', 'v');
addOptional(p, 'ptfRets',   0,    validNum);

% Parse them
parse(p, tcosts, ind, me, varargin{:});

if ~isnumeric(p.Results.weighting) 
    if ismember(p.Results.weighting,[{'v'},{'V'}])
        w = me;
    elseif ~isnumeric(p.Results.weighting) && ismember(p.Results.weighting,{'e','E'})
        w = me./me;
    else
        errorMessage = ['Error in calcTcosts().m. Optional weighting ', ...
                        'input should be one on of ''v'', ''V'', ''e'',', ...
                        '''E'', or a user-defined matrix that has the ', ...
                        'same dimensions as the tcosts matrix'];
        error(errorMessage);
    end  
elseif isequal(size(p.Results.weighting), size(me))
    w = p.Results.weighting;
else
    errorMessage = ['Error in calcTcosts().m. Optional weighting ', ...
                    'input should be one on of ''v'', ''V'', ''e'',', ...
                    '''E'', or a user-defined matrix that has the ', ...
                    'same dimensions as the tcosts matrix'];
    error(errorMessage);
end
        


% Store a few constants
nMonths = size(tcosts, 1);
nStocks = size(tcosts, 2);
nPtfs = max(max(ind));

% Initiate the trading costs, turnover and change in weight matrices
ptfTC = nan(nMonths, nPtfs);
ptfTO = nan(nMonths, nPtfs);
dWs = nan(nMonths, nStocks, nPtfs);

% Take all the rebalancing months
indRebMonths = find(sum(ind>0,2) > 0);

% Figure out the rebalancing frequency
rebFrequencies = indRebMonths - lag(indRebMonths,1,nan);
rebFrequencies(isnan(rebFrequencies)) = [];
rebFreq = mode(rebFrequencies);

% Store the increase in market capitalization. This is a shortcut to
% calculating the gross ex-dividend return
gretxd = me ./ lag(me, rebFreq, nan); 

% Loop over the portfolios
for i = 1:nPtfs
    
    % Initialize the weights for this portfolio
    thisPtfW = zeros(size(ind));
    
    % Assign the weights from the w matrix
    thisPtfW(ind == i) = w(ind == i);         
    
    % Calculate the sum of the weights & turn into a matrix
    sumThisPtfW = sum(thisPtfW, 2, 'omitnan');
    sumThisPtfWMat = repmat(sumThisPtfW, 1, nStocks);
    
    % Calculate the weights on the way out
    wOut = thisPtfW ./ sumThisPtfWMat;
    
    % Lag the outweights by the rebalancing frequency
    lagWOut = lag(wOut, rebFreq, 0);
    
    % Allow for increasing the base of the strategy to (1+r). This requires
    % the user to have passed on ptfRets with the correct dimensoins
    if size(p.Results.ptfRets, 1) == nMonths && ...
       size(p.Results.ptfRets, 2) == nPtfs
        wOut = wOut.*(1+repmat(p.Results.ptfRets(:,i), 1, nStocks)); 
    end
        
    % Calculate the weights on the way in: last month's weight times the
    % current month return ex-dividends
    wIn = lagWOut .* gretxd;           
    
    % Store the change in weights
    dWs(:,:,i) = wOut - wIn;    

    % Store the turnover and trading costs
    ptfTO(:,i) = sum(abs(dWs(:,:,i)), 2, 'omitnan');
    ptfTC(:,i) = sum(abs(dWs(:,:,i) .* tcosts), 2, 'omitnan');
end

% Calculate the net dW (dW(Long) - dW(Short))
if nargout > 2
    dW = dWs(:,:,end) - dWs(:,:,1); 
    dW(isnan(dW)) = 0;
end
