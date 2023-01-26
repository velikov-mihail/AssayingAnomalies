function [ptfRet,nStocks,ptfMarketCap] = calcPtfRets(ret,ind,mcap,hper,weighting)
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
%        -nStocks - matrix of number of firms in each portfolio               
%        -ptfMarketCap - matrix of total market capitalization of each portfolio              
%------------------------------------------------------------------------------------------
% Examples:
%
% [ptfRet,nStocks,ptfMarketCap] = calcPtfRets(ret,ind,me,1,'e') % Equal-weighted returns 
%                                                               with 1-month holding period                               
%------------------------------------------------------------------------------------------
% Dependencies:
%       N/A
%------------------------------------------------------------------------------------------
% Copyright (c) 2021 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2021, Assaying anomalies, Working paper.



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
nPtfs=max(max(ind));    
nMonths=size(ret,1);

% Carry over the index in case we are not rebalancing every month
for i=find(sum(lind>0,2)>0,1,'first')+1:nMonths
    if sum(lind(i,:)>0)==0
        lind(i,:)=lind(i-1,:);
    end
end

for i=1:nPtfs
    ptfInd=(lind==i);
    if hper>1
        for h=1:hper-1
            ptfInd=ptfInd | (lag(lind,h,0)==i);
        end
    end
    ptfInd=1*(ptfInd  & isfinite(lmcap)  & isfinite(ret));
    ptfInd(ptfInd==0)=nan;
    
    nStocks(:,i)=sum(isfinite(ptfInd),2);
    
    sumWeightingMcap=nansum(weightingMcap.*ptfInd,2);    
    ptfRet(:,i)=nansum( ptfInd.*ret.*weightingMcap ./ ...
                      repmat(sumWeightingMcap,1,size(weightingMcap,2)) ...
                      ,2);
    
    ptfMarketCap(:,i)=nansum(lmcap.*ptfInd,2);     
    
    ptfHasNoStocks=(nStocks(:,i)==0);
    
    nStocks(ptfHasNoStocks,i)=nan;
    ptfMarketCap(ptfHasNoStocks,i)=nan;   
    ptfRet(ptfHasNoStocks,i)=nan;
    
end

