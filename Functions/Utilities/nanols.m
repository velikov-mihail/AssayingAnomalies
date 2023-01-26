function res = nanols(y,x)
% PURPOSE: Utility function to estimated ordinary least squares regression.
% Output is the same as caling lscov(x,y,w), however it removes all rows in 
% [y x] that contain nan's
%------------------------------------------------------------------------------------------
% USAGE:   
% results = nanols(y,x)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -x - a matrix                                  
%        -y - a matrix
%------------------------------------------------------------------------------------------
% Output:
%        -res - a structure with OLS regression results 
%------------------------------------------------------------------------------------------
% Examples:
%
% OC = res = nanols(y,x,w)
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
ind = isnan([y x]);                       
ind = sum(ind,2)==0 ;                   

% Subset x & y
y = y(ind);
x = x(ind,:);


if size(y,1)<2 || size(x,1)<2 
    k = size(x,2) ; 
    res.meth  ='ols';
    res.y     = 0;
    res.nobs  = 0;
    res.nvar  = 0;
    res.beta  = nan*ones(k,1);
    res.yhat  = 0; 
    res.sige  = 0;
    res.bstd  = 0; 
    res.bint  = 0; 
    res.tstat = nan*ones(k,1); 
    res.rsqr  = 0;
    res.rbar  = 0; 
    res.rsqr  = 0;
    res.dw    = 0;  
else    
    res = ols(y,x);
end

