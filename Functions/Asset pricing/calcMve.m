function [weights, SR] = calcMve(rets) 
% PURPOSE: calculates optimal weights and Sharpe ratio from a set of asset
% returns
%---------------------------------------------------
% USAGE: [weights, SR] = calcMve(rets)     
%---------------------------------------------------
% Inputs
%        -rets - matrix with asset returns (nTimePeriods x nAssets)
% Outputs
%        -weights - vector of weights on each asset in the mean-variance
%                   efficient portfolio (1 x nAssets)
%        -SR - scalar indicating the Sharpe ratio of the mean-variance
%                   efficient portfolio (1 x 1)

% Drop the rows (e.g., months) in which we
indFinite = isfinite(sum(rets,2));
rets = rets(indFinite,:);

% Store the number of months and number of assets
% nMonths = size(rets, 1);
nAssets = size(rets, 2);

% Calculate a vector of the average returns, the variance-covaiance
% matrix
muR = mean(rets)';
SigmaR = cov(rets);

if nAssets > 1
    % Store a row vector of ones
    v1 = ones(1, nAssets);

    % Calculate the inverse covariance matrix
    SigmaRInv = SigmaR^(-1);

    % Calculate the weights
    weights = (SigmaRInv * muR) / (v1 * SigmaRInv * muR);

    % Calculate the Sharpe ratio
    SR = (weights' * muR) / sqrt(weights' * SigmaR * weights);
    
elseif nAssets == 1
    % Weight is 1 and sign depends on the average return
    weights = 1 * sign(muR);
    
    % Calculate the Sharpe ratio
    SR = weights * muR / sqrt(SigmaR);
else
    error('\nInput rets is empty.\n');    
end
    
