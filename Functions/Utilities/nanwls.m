function res = nanwls(y,x,w)
% PURPOSE: weighted least-squares regression 
%---------------------------------------------------
% USAGE: results = nanwls(y,x)
% Same as caling lscov(x,y,w), however it removes all rows in [y x] that contain nan's

ind=isnan([y x w]);                       % Get all the nan's
ind = sum(ind,2)==0 ;                   % Get the rows with nan's in them


y = y(ind);
x = x(ind,:);
w = w(ind);

nobs=length(y);
nvar=size(x,2);

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

