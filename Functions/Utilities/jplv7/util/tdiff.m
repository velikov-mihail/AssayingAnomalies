function dmat = tdiff(x,k)
% PURPOSE: produce matrix differences
% -----------------------------------------
% USAGE: dmat = tdiff(x,k)
% where:    x = input matrix (or vector) of length nobs
%           k = lagged difference order
% -----------------------------------------
% NOTE: uses trimr() and lag()
% -----------------------------------------
% RETURNS: dmat = matrix or vector, differenced by k-periods
%                 e.g. x(t) - x(t-k), of length nobs, 
%                 (first k observations are zero)
% -----------------------------------------
% SEE ALSO: trimr() modeled after Gauss trimr function
% -----------------------------------------

% written by:
% James P. LeSage, Dept of Economics
% University of Toledo
% 2801 W. Bancroft St,
% Toledo, OH 43606
% jlesage@spatial-econometrics.com

% Stephan Siegel [ss1110@columbia.edu]
% provided a bug fix for this function
% July, 2004

% error checking on inputs
if (nargin ~= 2)
 error('Wrong # of arguments to tdiff');
end;

[nobs nvar] = size(x);

if ( k == 0)
 dmat = x;
else
 dmat = zeros(nobs,nvar);
 dmat(1+k:nobs,:) = x(1+k:nobs,:)- trimr(lag(x,k),k,0);
end;

