% PURPOSE: An example of using rvarf_g(), 
%          Gibbs estimates and forecast using
%          a vector autoregressive model                                                 
%          (with random-walk averaging prior)                    
%---------------------------------------------------
% USAGE: bvarf_gd
%---------------------------------------------------

load test.dat; % a test data set containing
               % monthly mining employment for
               % il,in,ky,mi,oh,pa,tn,wv
% data covers 1982,1 to 1996,5
dates = cal(1982,1,12);

vnames = strvcat('il','in','ky','mi','oh','pa','tn','wv');

y = test;
[nobs neqs] = size(y);

nlag = 2;  % number of lags in var-model

% prior hyperparameters
% priors for contiguous variables:  N(w(i,j),sig) for 1st own lag
%                                  N(  0 ,tau*sig/k) for lag k=2,...,nlag
%               
% priors for non-contiguous variables are:  N(w(i,j) ,theta*sig/k) for lag k 
%  
% e.g., if y1, y3, y4 are contiguous variables in eq#1, y2 non-contiguous
%  w(1,1) = 1/3, w(1,3) = 1/3, w(1,4) = 1/3, w(1,2) = 0
%                                              
% typical values would be: sig = .1-.3, tau = 4-8, theta = .5-1  
sig = 0.1;
tau = 6;
theta = 0.5;
freq = 12;   % monthly data

% this is an example of using 1st-order contiguity
% of the states as weights to produce prior means

W=[0      0.5    0.5    0     0     0    0     0
   0.25   0      0.25   0.25  0.25  0    0     0
   0.20   0.20   0      0     0.20  0    0.20  0.20
   0      0.50   0      0     0.50  0    0     0
   0      0.20   0.20   0.20  0     0.20 0.20  0.20
   0      0      0      0     0.50  0    0     0.50
   0      0      1      0     0     0    0     0
   0      0      0.33   0     0.33  0.33 0     0];

% estimate the model
prior.w = W;
prior.sig = sig;
prior.tau = tau;
prior .theta = theta;
prior.freq = 12;
prior.rval = 50;  % homoscedastic prior
% prior.rval = 4; % heteroscedastic prior

ndraw = 1100;
nomit = 100;
begf = ical(1995,1,dates);  % beginning forecast date
nfor = 12;                  % # of forecasts
endf = ical(1995,12,dates); % end forecast dates

% straight bvar model in levels
yfor1 = rvarf(y,nlag,W,freq,nfor,begf,sig,tau,theta);

% estimate the model
yfor2 = rvarf_g(y,nlag,nfor,begf,prior,ndraw,nomit);

rnames = 'Dates';
for i=begf:endf
rnames = strvcat(rnames,tsdate(dates,i));
end;
in.rnames = rnames;
in.fmt = '%9.3f';
in.cnames = vnames;
fprintf(1,'rvar forecasts \n');
mprint(yfor1,in);
fprintf(1,'rvar Gibbs forecasts \n');
mprint(yfor2,in);




