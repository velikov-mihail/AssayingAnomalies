function m = nanmatsum(x,y)
% PURPOSE: Utility function to add two matrices by allowing for NaNs in one
% of them
%------------------------------------------------------------------------------------------
% USAGE:   
% m = nanmatsum(x,y)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -x - a matrix                                  
%        -y - a matrix
%------------------------------------------------------------------------------------------
% Output:
%        -m - a matrix equal to the sum of x and y where m is NaN only if
%        both x and y are NaN
%------------------------------------------------------------------------------------------
% Examples:
%
% OC = nanmatsum(COGS,XSGA); % Don't want to make NaN observations in which XSGA is NaN
%------------------------------------------------------------------------------------------
% Dependencies:
%       N/A
%------------------------------------------------------------------------------------------
% Copyright (c) 2022 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2022, Assaying anomalies, Working paper.

[rx, cx] = size(x);
[ry, cy] = size(y);

if (rx == ry && cx == cy)
    xv = reshape(x,1,rx*cx);
    yv = reshape(y,1,rx*cx);
    m = reshape(nansum([xv;yv]),rx,cx);
    if nargin == 2
        index = (isnan(xv) & isnan(yv));
        m(index) = nan;
    end
else
    disp(['Error: matricies are not the same dimensions.'])
end
