% PURPOSE: demo of raftery()
%          Raftery and Lewis convergence diagnostics
% 
%---------------------------------------------------
% USAGE: raftery_d
%---------------------------------------------------

n=100; k=3; % set number of observations and variables
randn('seed',10101);
x = randn(n,k); b = ones(k,1); % generate data set
randn('seed',20201);
y = x*b + randn(n,1);
ndraw = 600; nomit = 100; % set the number of draws   
r = [1.0 1.0 1.0]'; % prior b means
R = eye(k); 
T = eye(k);         % prior b variance 
rval = 2;           % hetroscedastic prior for r-value
prior.beta = r;
prior.bcov = T;
prior.rmat = R;
prior.rval = rval;
% generate some Gibbs draws
result = ols_g(y,x,ndraw,nomit,prior);
vnames = strvcat('beta1','beta2','beta3');

q = 0.025; r = 0.005; s = 0.95;
res = raftery(result.bdraw,q,r,s);
prt(res,vnames);

