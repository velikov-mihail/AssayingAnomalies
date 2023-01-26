function result = normrt_rnd(mu,sigma2,right)
% PURPOSE: compute random draws from a right-truncated normal
%          distribution, with mean = mu, variance = sigma2
% ------------------------------------------------------
% USAGE: y = normrt_rnd(mu,sigma2,right)
% where: nobs = # of draws
%          mu = mean     (scalar or vector)
%      sigma2 = variance (scalar or vector)
%       right = right truncation point (scalar or vector)
% ------------------------------------------------------
% RETURNS: y = (scalar or vector) the size of mu, sigma2
% ------------------------------------------------------
% NOTES: This is merely a convenience function that
%        calls normt_rnd with the appropriate arguments
% ------------------------------------------------------



% written by:
% James P. LeSage, Dept of Economics
% University of Toledo
% 2801 W. Bancroft St,
% Toledo, OH 43606
% jpl@jpl.econ.utoledo.edu

if nargin ~= 3
error('normrt_rnd: Wrong # of input arguments');
end;

left = mu - 5*sqrt(sigma2);

result = normt_rnd(mu,sigma2,left,right);

 
