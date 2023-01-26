function R = makePastPerformance(ret,from,to)  
% PURPOSE: This function calculates cumulative returns 
%------------------------------------------------------------------------------------------
% USAGE:   
% R = makePastPerformance(ret,from,to)  
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -ret - a matrix of stock returns                                  
%        -from - starting lag for cumulative returns                                
%        -to - end lag for cumulative returns                             
%------------------------------------------------------------------------------------------
% Output:
%        -R - a matrix with the cumulative returns
%------------------------------------------------------------------------------------------
% Examples:
% R = makePastPerformance(ret,12,1);      % Classic momentum: from 12 month
%                                           ago to one month ago (NOT including last month)
% R62 = makePastPerformance(ret,6,1);     % Recent horizon momentum: from 6 month ago to 1 
%                                           month ago
% R127 = makePastPerformance(ret,12,6);   % Intermediate horizon momentum: from 12 month 
%                                           ago to 6 months ago 
% R3613 = makePastPerformance(ret,36,12); % DeBont and Thaler long run reversals: from 36 
%                                           months ago to 12 months ago
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

% calculates cumulative returns 
if from-to==1
    
    if from == 1
        R = ret;
    else
        R = lag(ret,to);
        R(1:from-1,:) = nan;
    end
    
else    
    isNanInd = isnan(ret);
    ret(isNanInd) = 0;
    tret = log(1 + ret);
    if to == 0
        RR = tret;
    else
        RR = lag(tret,to,nan);
    end
    for i = to+1:from-1
        RR = RR + lag(tret,i,nan);
    end
    R = RR;
    R(1:from-1,:) = nan;
    R(isNanInd) = nan;
    R = exp(R);
end

