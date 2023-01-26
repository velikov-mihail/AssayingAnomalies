% SQPLOT: Given a configuration of points, changes the current plot so as to be
%         square, with axis of equal units, maximally containing the 
%         configuration.
%
%     Syntax: bounds = sqplot(x,y,{buffer},{noadj})
%                 OR
%             bounds = sqplot([x,y],{buffer},{noadj})
%
%         x,y    = vectors of X and Y coordinates of point configuration.
%         buffer = scalar indicating the percent-range buffer to be inserted
%                   on both sides of the point configuration (default=5).
%         noadj = boolean flag indicating, if true, that the axis bounds are to 
%                   be returned but the current plot is not to be adjusted 
%                   [default = 0].  Adjustment can be done later by: 
%                       axis(bounds)
%                       axis('square')
%        ----------------------------------------------------------------------
%        bounds = row vector of plot bounds: [xmin,xmax, ymin,ymax]
%

% RE Strauss, 9/20/97
%   1/2/00 -  changed handling of input arguments.
%   1/4/00 -  make adjustment of current plot, optionally allowing the 
%               adjustment to be skipped.

function bounds = sqplot(x,y,buffer,noadj)
  if (nargin < 2) y = []; end;
  if (nargin < 3) buffer = []; end;
  if (nargin < 4) noadj = []; end;

  if (~isvector(x) & (isempty(y) | isscalar(y)))
    noadj = buffer;
    buffer = y;
    y = x(:,2);
    x = x(:,1);
  end;

  if (isempty(buffer))                  % Default percent-buffer
    buffer = 0.05;
  elseif (buffer > 1)                   % If percentage, convert to
    buffer = buffer/100;                %   proportion
  end;
  if (isempty(noadj))
    noadj = 0;
  end;

  [xr,xc] = size(x);                    % x,y must be column vectors
  [yr,yc] = size(y);                    %   of same length
  if (min([xr,xc])>1 | min([yr,yc])>1)
    error('  SQPLOT: X and Y must be column vectors');
  end;
  if (max([xr,xc]) ~= max([yr,yc]))
    error('  SQPLOT: X and Y vectors must be same length');
  end;
  if (xc > 1)
    x = x';
  end;
  if (yc > 1)
    y = y';
  end;

  min_crds =   min([x y]);
  max_crds =   max([x y]);
  mid_crds =   (min_crds + max_crds)/2;
  range_crds = max_crds - min_crds;

  if (range_crds(1) > range_crds(2));     % X range greater
    xmin = min_crds(1) - range_crds(1)*buffer;
    xmax = max_crds(1) + range_crds(1)*buffer;
    half_span = (xmax-xmin)/2;
    ymin = mid_crds(2) - half_span;
    ymax = mid_crds(2) + half_span;
  else                                   % Y range greater
    ymin = min_crds(2) - range_crds(2)*buffer;
    ymax = max_crds(2) + range_crds(2)*buffer;
    half_span = (ymax-ymin)/2;
    xmin = mid_crds(1) - half_span;
    xmax = mid_crds(1) + half_span;
  end;

  bounds = [xmin xmax ymin ymax];

  if (~noadj)
    axis(bounds);
    axis('square');
  end;

  return;

