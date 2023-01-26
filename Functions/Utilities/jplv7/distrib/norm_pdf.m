function pdf = norm_pdf (x, m, v)
% PURPOSE: computes the normal probability density function 
%          for each component of x with mean m, variance v
%---------------------------------------------------
% USAGE: pdf = norm_pdf(x,m,v)
% where: x = variable vector (nx1)
%        m = mean vector (default=0)
%        v = variance vector (default=1)
%---------------------------------------------------
% RETURNS: pdf (nx1) vector
%---------------------------------------------------
% SEE ALSO: norm_d, norm_rnd, norm_inv, norm_cdf
%---------------------------------------------------

% Written by TT (Teresa.Twaroch@ci.tuwien.ac.at) on Jun 3, 1993
% Updated by KH (Kurt.Hornik@ci.tuwien.ac.at) on Oct 26, 1994
% Copyright Dept of Probability Theory and Statistics TU Wien
% Updated by James P. Lesage, 
% jlesage@spatial-econometrics.com 1/7/97


  if ~((nargin == 1) | (nargin == 3))
    error('Wrong # of arguments to norm_pdf');
  end

  [r, c] = size (x);

  if (nargin == 1)
    m = zeros(r,1);
    v = ones(r,1);
  end

  pdf = zeros (r,1);

    pdf(1:r,1) = stdn_pdf((x(1:r,1) - m(1:r,1)) ./ sqrt (v(1:r,1))) ...
 ./ sqrt (v(1:r,1)); 

  
