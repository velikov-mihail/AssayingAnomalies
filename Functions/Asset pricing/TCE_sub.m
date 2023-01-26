function [costs TO] = TCE_sub(retx,ind,tcosts,me,vw,i) 
% PURPOSE: function that calculates transactions costs and portfolio
% turnover
%---------------------------------------------------
% USAGE:   [costs TO] = TCE(ind,tcosts,me,vw,i)     
%      
%---------------------------------------------------
% Inputs:
%        -ind - a matrix of indexes                                        (nt x nobs)
%        -tcosts - a matrix containing the transaction costs               (nt x nobs)
%        -me - a matrix of market cap numbers                              (nt x nobs)
%        -vw - 1 or 2 indicating value- or equal-weighting                 (1 x 1)
%        -i -             (1 x 1) 
% Output:
%        -costs - a matrix that contains the transcation costs for the
%                   portfolios                                             (nt x nobs)
%        -TO - a matrix that contains the portfolio turnover on both the
%               short and long sides                                       (nt x 2)  

% rebalance freq
temp = find(sum(ind>0,2) > 0);                                             % Take all the months that have index values
temp = temp - lag(temp,1,nan); temp(isnan(temp)) = [];
freq = mode(temp);                                                         % freq % MV take the mode of every column                          
gretxd = retx+1;

V = zeros(size(ind));

if vw == 1 % value weight
    V(ind == i) = me(ind == i);
    V(isnan(V)) = 0; % need this for stocks w/o me
else % equal weight
    V(ind == i) = 1;
end

D = nansum(V,2);                                    % Take the sum of the me in the cross-section
Wout = V./repmat(D,1,size(V,2));                    % Divide each observation by that sum
Win = lag(Wout,freq,0).*gretxd;                     % Lag it by the frequency and multiply by the gross ret ex-div
Win = Win./repmat(nansum(Win')',1,cols(V));         % Divide by it again?

dW = Wout - Win;                                    
dW(dW == 0) = nan;

TO = nansum(abs(dW'))';
costs = nansum(abs(dW'.*tcosts'))';
% ttemp = nan(size(tcosts));
% ttemp(isfinite(dW)) = tcosts(isfinite(dW));
% [sum(isfinite(tcosts),2) sum(isfinite(dW),2) nansum(abs(dW'))' nanmean(ttemp')' nansum(abs(dW'.*tcosts'))']
end