function pdf = stdn_pdf(x)
% PURPOSE: computes the standard normal probability density
%          for each component of x with mean=0, variance=1
%---------------------------------------------------
% USAGE: cdf = stdn_pdf(x)
% where: x = variable vector (nx1)
%---------------------------------------------------
% RETURNS: pdf == (nx1) vector containing pdf for each x
%---------------------------------------------------

% Written by TT (Teresa.Twaroch@ci.tuwien.ac.at) 
% Updated by KH (Kurt.Hornik@ci.tuwien.ac.at) 
% Converted to MATLAB by James P. Lesage, jpl@jpl.econ.utoledo.edu 


  if (nargin ~= 1)
    error('Wrong # of arguments to stdn_pdf');
  end;
  
  [r, c] = size(x);
  s = r * c;
  x = reshape(x, 1, s);
  pdf = zeros(1, s);
  
  k = find (isnan(x));
  if any (k)
    pdf(k) = NaN * ones(1, length(k));
  end;
  
  k = find (~isinf(x));
  if any (k)
    pdf(k) = (2 * pi)^(- 1/2) * exp( - x(k) .^ 2 / 2);
  end;
  
  pdf = reshape(pdf, r, c);
  
