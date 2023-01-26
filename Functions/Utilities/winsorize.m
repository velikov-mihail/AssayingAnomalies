function wdata = winsorize(data,n) 
% PURPOSE: Utility function to winsorize rows in a matrix
%------------------------------------------------------------------------------------------
% USAGE:   
% wdata = winsorize(data,n)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -data - a matrix                                  
%        -n - percentile to trim at
%------------------------------------------------------------------------------------------
% Output:
%        -tdata - winsorized matrix
%------------------------------------------------------------------------------------------
% Examples:
%
% ret = winsorize(ret, 1); % Winsorize top and bottom 1% in each month
%------------------------------------------------------------------------------------------
% Dependencies:
%       N/A
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

% Get the bottom and top percentiles
a = [n 100-n]; 

% Loop through each row
for j = 1:size(data, 1)
    b = data(j,:);

    if sum(~isnan(b))>0
        p = prctile(b,a);
        b(b < p(1)) = p(1);
        b(b > p(2)) = p(2);
        data(j, :) = b;
    end
end

% Assign the output matrix
wdata = data;



    
