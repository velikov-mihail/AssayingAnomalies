function indout = make_sS(indin, NN, indin2)
% PURPOSE: Creates a buy/hold indicator
%------------------------------------------------------------------------------------------
% USAGE: indout = make_sS(indin, NN, indin2);
%------------------------------------------------------------------------------------------
% Inputs:
%        -indin - an index matrix, specifying the portfolio each stock/month corresponds to                          
%        -NN - Number of portfolios to buy
% Output:
%        -indout - an index matrix, accounting for buy/hold  
%------------------------------------------------------------------------------------------
% Examples:
%
% indout = make_sS(indin, Nprts); make sS holding top Nprts
% indout = make_sS(indin, Nprts, indin2); delays sales (short covers) on the margin if indin2 looks good (bad)
%   can also be used to make an sS strategy using a second indicator to determine the s boundary  
% indout = make_sS(indin, [Nprt1 Nprt2], indin2); trades indin2 on the boundary of indin trades
%   accelerates buys if in top Nprt1 of indin and in top Nprt2 of indin2
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


% 
% 
% 

% disp(['test']);
indt = indin; N = max(max(indt));

if nargin == 3
    indtt = indin2; N2 = max(max(indtt));
else
    indtt = indt; N2 = N;
end

M = max(size(NN));
if M == 1
    Nprt1 = 0;
    Nprt2 = NN;
else % this delays sales (short covers) on the margin
    Nprt1 = NN(1);
    Nprt2 = NN(2);
end

index = find(sum(indt,2)>0);
for i = 2:rows(index)
    
    index2 = (indt(index(i-1),:) >= N - Nprt1 & indtt(index(i),:) >= N2 + 1 - Nprt2);
    indt(index(i),index2 == 1) = N; % slow sales / speeds purchases
    
    index2 = (indt(index(i-1),:) <= 1 + Nprt1 & indt(index(i-1),:) > 0 ...
              & indtt(index(i),:) <= Nprt2 & indtt(index(i),:) > 0);
    indt(index(i),index2 == 1) = 1; % slow short covers / speeds shorting
        
    index2 = (indt(index(i-1),:) < N & indt(index(i),:) == N ...
        & indtt(index(i),:) <= Nprt2 & indtt(index(i),:) > 0);
    indt(index(i),index2 == 1) = N-1; % slow buys
    
    index2 = (indt(index(i-1),:) > 1 & indt(index(i),:) == 1 ...
        & indtt(index(i),:) >= N2 + 1 - Nprt2);
    indt(index(i),index2 == 1) = 2; % slow shorting
        
end

indout = indt;

end
