function res = nanwls(y,x,w)
% PURPOSE: Utility function to estimated weighted-least squares regression.
% Output is the same as caling lscov(x,y,w), however it removes all rows in 
% [y x] that contain nan's
%------------------------------------------------------------------------------------------
% USAGE:   
% results = nanwls(y,x)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -x - a matrix of independent, RHS variables                                  
%        -y - a vector of dependent, LHS variable
%        -w - a vector of weights
%------------------------------------------------------------------------------------------
% Output:
%        -res - a structure with WLS regression results 
%------------------------------------------------------------------------------------------
% Examples:
%
% OC = res = nanwls(y,x,w)
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

% Get the rows with nan's in them
ind = isnan([y x w]);                       
ind = sum(ind,2)==0;                   

% Subset
y = y(ind);
x = x(ind,:);
w = w(ind);

nobs = length(y);
nvar = size(x,2);

[beta,bstde,mse] = lscov(x,y,w);

res.meth = 'wls';
res.y = y;
res.nobs = nobs;
res.nvar = nvar;
res.beta=beta;
res.yhat = x*res.beta;
res.resid = y - res.yhat;
sigu = res.resid'*res.resid;
res.bstde = bstde;
res.tstat = res.beta./res.bstde;
ym = y - mean(y);
rsqr1 = sigu;
rsqr2 = ym'*ym;
res.rsqr = 1.0 - rsqr1/rsqr2; % r-squared
rsqr1 = rsqr1/(nobs-nvar);
rsqr2 = rsqr2/(nobs-1.0);
if rsqr2 ~= 0
    res.rbar = 1 - (rsqr1/rsqr2); % rbar-squared
else
    res.rbar = res.rsqr;
end
res.mse=mse;

