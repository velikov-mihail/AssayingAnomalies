function res = nanols(y,x)
% PURPOSE: least-squares regression 
%---------------------------------------------------
% USAGE: results = nanols(y,x)
% Same as ols(x,y), however it removes all rows in [y x] that contain nan's

ind=isnan([y x]);                       % Get all the nan's
ind = sum(ind,2)==0 ;                   % Get the rows with nan's in them


y = y(ind);
x = x(ind,:);


if size(y,1)<2 | size(x,1)<2 ; 
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

