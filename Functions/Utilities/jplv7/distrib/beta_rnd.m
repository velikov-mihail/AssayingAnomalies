function rnd = beta_rnd (n, a, b)
% PURPOSE: random draws from the beta(a,b) distribution
%--------------------------------------------------------------
% USAGE: rnd = beta_rnd(n,a,b)
% where:   n = size of the vector of draws
%          a = beta distribution parameter, a = scalar 
%          b = beta distribution parameter  b = scalar 
% NOTE: mean = a/(a+b), variance = ab/((a+b)*(a+b)*(a+b+1))
%--------------------------------------------------------------
% RETURNS: n-vector of random draws from the beta(a,b) distribution
%--------------------------------------------------------------
% SEE ALSO: beta_d, beta_pdf, beta_inv, beta_rnd
%--------------------------------------------------------------

% written by:
% James P. LeSage, Dept of Economics
% University of Toledo
% 2801 W. Bancroft St,
% Toledo, OH 43606
% jlesage@spatial-econometrics.com

   
  if (nargin ~= 3)
  error('Wrong # of arguments to beta_rnd');
  end;
  
if any(any((a<=0)|(b<=0)))
   error('Parameter a or b is nonpositive')
end

a1n = gamm_rnd(n,a,1);
a1d = gamm_rnd(n,b,1);
rnd = a1n./(a1n+a1d);

