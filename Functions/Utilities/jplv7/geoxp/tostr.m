% TOSTR: Converts a vector of integer or real numbers to a text matrix.
%
%     Syntax: textmat = tostr(A,{digits},{leftjust})
%
%         A =        single matrix to be converted.
%         digits =   optional number of significant digits [default=8].
%         leftjust = optional booloean flag indicating, if true, that values are 
%                      to be left justified within text string (i.e., padded with 
%                      blanks on the right) [default = 0 = right-justified].
%         ------------------------------------------------------------------------
%         textmat =  corresponding matrix of text strings.
%

% RE Strauss, 6/24/98
%   1/10/00 - allow to specify extra appended digits of zeros.

function textmat = tostr(A,digits,leftjust)
  if (nargin < 2) digits = []; end;
  if (nargin < 3) leftjust = []; end;

  digits_given = 1;
  if (isempty(digits))
    digits = 8;
    digits_given = 0;
  end;
  if (isempty(leftjust))
    leftjust = 0;
  end;

  [r,c] = size(A);
  if (min([r c]) > 1)
    error('  TOSTR: numeric input must be a vector');
  elseif (r==1)                       % Transpose row vector to column vector
    A = A';
  end;
  lenA = length(A);

  all_finite = 1;
  if (any(~finite(A)))                  % If any missing values,
    miss = find(~finite(A));            % Save position
    A(miss) = ones(length(miss),1);     % Temporarily replace by ones
    all_finite = 0;
  end;
    
  minA = min(A);                      % Min & max values
  maxA = max(abs(A));               
  if (maxA < eps)                     % Substitute eps for max of vector of zeros
    maxA = eps;
  end;

  B = A;
  if (~all_finite)
    A(miss) = NaN * ones(length(miss),1); % Restore missing values
  end;

  f = max(floor(log10(maxA)+eps)+1,1);    % Number of digits before decimal point
  d = max([digits-f;zeros(1,length(f))]); % Number of digits after  decimal point
  if (minA < 0)                           % If any values <0,
    f = f+1;                              %   allow for sign
  end;
  if (maxA < 1)                           % If all values < 1, allow full number of digits
    d = d+1;                              %   despite leading zero
  end;

  if (~digits_given & isintegr(B))        % If vector of all integers
    w = f;
    d = 0;
    editstr = ['%',int2str(w),'.0f'];
  else                                    % If real numbers, full number of digits
    if (~digits_given)
      epsilon = 10.^(-d-1);
      for k = 1:d
        BB = B * 10^k;
        e = epsilon * 10^k;
        if (isintegr(BB,e))
          d = k;
          break;
        end;
      end;
    end;
    w = f+d+1;
    editstr = ['%',int2str(w),'.',int2str(d),'f'];
  end;

  textmat = [];                             % Prepare for conversion to string
  for i = 1:lenA                            % Loop through numeric values
    if (finite(A(i)))                       % If value is numeric,
      s = sprintf(editstr,A(i));              % Convert number to string
      if (leftjust)                           % If value is to be left-justified in string,
        bl = isspace(s);                        % Find positions of blanks
        cbl = sum(bl);                          % Count number of blanks
        s = [s(~bl), blanks(cbl)];              % Move non-blanks forward, pad behind with blanks
      end;
      textmat = [textmat; s];                 % Append onto output matrix
    else                                    % Else if values is not finite,
      textmat = [textmat; blanks(w)];         % Use string of blanks
    end;
  end;

  return;
