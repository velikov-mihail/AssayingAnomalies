function ind = assignToPtf(x,pp)
% PURPOSE: Function that assigns each firm-month to the bin it belongs to in the
% particular month. It assigns a zero if a firm-month is not held in any
% portfolio.
%------------------------------------------------------------------------------------------
% USAGE: 
% index = assign(x,pp)
%------------------------------------------------------------------------------------------
% Inputs
%        -x -matrix based on which we want to assign the bins 
%        -pp -a matrix with the breakpoints (values) for each time period
% Output
%        -ind -a matrix that indicates the bin each stock-time is in
%------------------------------------------------------------------------------------------
% Examples:
%
% ind = assignToPtf(me,prctile(me,[20 40 60 80],2)) % Quintile sort on size
%------------------------------------------------------------------------------------------
% Dependencies:
%       Uses N/A
%------------------------------------------------------------------------------------------
% Copyright (c) 2021 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2021, Assaying anomalies, Working paper.


ind = zeros(size(x));                        % Create a matrix with the same dimensions as x
L1 = pp(:,1);                                % Take the first column of pp - the first bp values for all time periods
L1 = repmat(L1,1,size(x,2));                 % Make it a matrix with as many col's as the number of firms                  
ind(x<L1)=1;                                 % Note all the firms in the first bin

for j = 1:size(pp,2)-1                       % Repeat the same for all the breakpoints without the last one
    L = repmat(pp(:,j),1,size(x,2));
    ind(x>=L) = j+1;
end

Uend = repmat(pp(:,end),1,size(x,2));
ind(x>=Uend)=size(pp,2)+1;






