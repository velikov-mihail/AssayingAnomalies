% MDSFUNC: Objective function for MDS.  Given the target distance matrix and
%           a set of point coordinates in p dimensions, calculates the metric
%           STRESS (standardized residual sum of squares).
%
%       Usage: stress = mdsfunc(crd,target_dist,no_norm)
%
%           crd =         [p*n] vector of MDS coordinates for n points in p
%                           dimensions, concatenated by dimension
%           target_dist = [n x n] symmetric matrix of target distances 
%                           (proximities)
%           no_norm =     flag indicating that stress is not to be normalized
%                           (=1); default is normalization, which is used for
%                           objective function
%

% RE Strauss, 8/1/95
%   8/20/99 - miscellaneous changes for consistency with Matlab v5.

% Krzanowski and Marriott (1994), pp. 111-112.

function stress = mdsfunc(crd,target_dist,no_norm)
  if (nargin < 3)
    no_norm = 0;
  end;

  n = size(target_dist,1);
  p = round(length(crd)/n);
  crd = reshape(crd,n,p);

  % Convert prox to column vector of lower triangular portion 
  prx = trilow(target_dist);

  % Convert mds coords to distance matrix, convert to column vector
  dist = zeros(n,n);
  for i=1:(n-1)
    for j=(i+1):n
      dist(j,i) = sqrt(sum((crd(i,:)-crd(j,:)).^2));
    end;
  end;
  y = trilow(dist);

  resid = y-prx;

  if (no_norm)
    stress = sqrt(resid'*resid);             % Raw
  else
    stress = sqrt((resid'*resid) / (y'*y));  % Normalized
  end;

  return;
