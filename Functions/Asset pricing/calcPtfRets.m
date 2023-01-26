function [ptfRet, ptfNumStocks, ptfMarketCap] = calcPtfRets(ret, ind, mcap, hper, weighting)
% PURPOSE: Calculates portfolio returns, number of stocks, and market
% capitalizations for each portfolio indicated by ind
%------------------------------------------------------------------------------------------
% USAGE : [pret, nStocks, ptfMarketCap] = calcPtfRets(ret,ind,k,mv);
%------------------------------------------------------------------------------------------
% Inputs:
%        -ret - a matrix of stock returns                          
%        -ind - a matrix of portfolio index                               
%        -mcap - a matrix of market capitalization numbers                             
%        -hper - a scalar indicating the ptf holding period               
%        -weighting - weighting scheme (one of {'V','v', 'E','e'})
% Output:
%        -pret - matrix of RAW value-weighted portfolio returns      
%        -ptfNumStocks - matrix of number of firms in each portfolio               
%        -ptfMarketCap - matrix of total market capitalization of each portfolio              
%------------------------------------------------------------------------------------------
% Examples:
%
% [ptfRet, ptfNumStocks, ptfMarketCap] = calcPtfRets(ret, ind, me, 1, 'e') % Equal-weighted returns 
%                                                                            with 1-month holding period                               
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

% Lag market cap and the portfolio index
lmcap = lag(mcap,1,nan);                                                        
lind = lag(ind,1,0);

% Check weighting scheme
if strcmp(weighting,'e')
    weightingMcap = ones(size(mcap));
else
    weightingMcap = lmcap;    
end

% Store a couple of variables
nPtfs = max(max(ind));    
[nMonths, nStocks] = size(ret);

% Carry over the index in case we are not rebalancing every month
nNonZero = sum(lind>0, 2);
indReb = find(nNonZero);
rebFreq = mode(indReb - lag(indReb, 1, nan));
startMonth = find(nNonZero>0, 1, 'first') + 1;
endMonth = min(find(nNonZero>0, 1, 'last') + rebFreq, nMonths);
for i=startMonth:endMonth
    if nNonZero(i)==0
        lind(i,:) = lind(i-1,:);
    end
end

% Initialize the output matrices
ptfNumStocks = nan(nMonths, nPtfs);
ptfMarketCap = nan(nMonths, nPtfs);
ptfRet = nan(nMonths, nPtfs);

% Loop over the portfolios
for i=1:nPtfs
    % For this portfolio
    ptfInd = (lind==i);

    % Carry over the index if holding period higher than 1
    if hper>1
        for h=1:hper-1
            ptfInd = ptfInd | (lag(lind,h,0)==i);
        end
    end

    % Make sure we are only using stock-months with available lagged market
    % cap & return observations
    ptfInd = 1 * (ptfInd           & ...
                  isfinite(lmcap)  & ...
                  isfinite(ret));
    ptfInd(ptfInd==0) = nan;

    % Calculate the number of stocks
    ptfNumStocks(:, i) = sum(isfinite(ptfInd),2);
    
    % Calculate the portfolio return
    sumWghtMcap = sum(weightingMcap.*ptfInd, 2, 'omitnan');    
    rptdSumWghtMcap = repmat (sumWghtMcap, 1, nStocks);
    ptfRet(:,i) = sum( ptfInd.*ret.*weightingMcap ./ ...
                       rptdSumWghtMcap, ...
                       2, 'omitnan');
    
    % Calculate the portfolio market cap
    ptfMarketCap(:,i) = sum(lmcap.*ptfInd, 2, 'omitnan');       
    
    % Set to NaN stock-months with no stocks in the portfolio
    ptfHasNoStocks = (ptfNumStocks(:,i)==0);    
    ptfNumStocks(ptfHasNoStocks, i) = nan;
    ptfMarketCap(ptfHasNoStocks, i) = nan;   
    ptfRet(ptfHasNoStocks, i) = nan;
    
end

