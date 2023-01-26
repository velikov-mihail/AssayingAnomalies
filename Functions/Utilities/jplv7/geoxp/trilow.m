% TRILOW: Extracts the lower triangular portion (without diagonal) of a
%         square symmetric matrix into a columnwise column vector.
%         Optionally returns corresponding subscripts.
%         If given a scalar, returns it.
%
%         Use trisqmat() to reverse the extraction.
%
%     Usage: [c,i,j] = trilow(x)
%

% RE Strauss, 1/13/96
%   8/20/99 - subscripting changes due to new Matlab v5 conventions.

function [c,i,j] = trilow(x)
  [n,p] = size(x);
  if (n~=p)
    error('  Matrix must be square');
  end;

  if (n==1)
    c = x;
  else
    t = tril(ones(n)) - eye(n);
    t = t(:);
    x = x(:);
    c = x(t==1);
  end;

  if (nargout>1)
    i = ones(length(c),1);
    j = i;
    k = 0;
    for jj = 1:(n-1)
      for ii = (jj+1):n
        k = k+1;
        i(k) = ii;
        j(k) = jj;
      end;
    end;
  end;

  return;
