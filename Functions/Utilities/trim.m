function tdata = trim(data,n)
% PURPOSE: Utility function to trim (i.e., set to NaN) rows in a matrix
%------------------------------------------------------------------------------------------
% USAGE:   
% tdata = trim(data,n)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -data - a matrix                                  
%        -n - percentile to trim at
%------------------------------------------------------------------------------------------
% Output:
%        -tdata - trimmed matrix
%------------------------------------------------------------------------------------------
% Examples:
%
% ret = trim(ret,1); % Remove top and bottom 1% in each month
%------------------------------------------------------------------------------------------
% Dependencies:
%       N/A
%------------------------------------------------------------------------------------------
% Copyright (c) 2021 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2021, Assaying anomalies, Working paper.


a = [n 100-n]; 

for j = 1:size(data,1)
    b = data(j,:);

    if sum(~isnan(b))>0
        p = prctile(b,a);
        b(b<p(1)) = nan;
        b(b>p(2)) = nan;
        data(j,:) = b;
    end
end

tdata = data;



    
