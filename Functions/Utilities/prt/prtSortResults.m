function prtSortResults(res,lsprt)
% PURPOSE: Utility function to optionally print results by runUnivSort()
%------------------------------------------------------------------------------------------
% USAGE:   
% plotStrategyFigs(res)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -res - a structure output by runUnivSort()
%------------------------------------------------------------------------------------------
% Output:
%        -N/A
%------------------------------------------------------------------------------------------
% Examples:
%
% plotStrategyFigs(res)
%------------------------------------------------------------------------------------------
% Dependencies:
%       Used by runUnivSort()
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

if lower(res.w) == 'e'
    www = 'Equally-weighted ';
elseif lower(res.w) == 'v'
    www = 'Value-weighted';
end 



if length(res.factorModel)==1 % Means one of the FF ones
    mdl=['Fama and French ',char(num2str(res.nFactors)),'-factor model'];
    if res.factorModel==1
        mdl=['CAPM'];
    end    
else
    mdl=['User-defined ',char(num2str(res.nFactors)),'-factor model'];
end
heads=[res.factorLoadings.label];


X = [res.xret  res.alpha [res.factorLoadings.b]];
T = [res.txret res.talpha [res.factorLoadings.t]];

% for i=1:res.nfactors
%       res.loadings(i).label=heads(i);
% end

fmtb  ='%7.3f' ;
fmt ='[%5.2f]' ;
S = strvcat('  ', '  ') ;
S1 = strvcat(' ') ;
B = [];
C = [] ;
for j = 1:rows(X) 
    A = [];
    for i = 1:cols(X) 
        A = [A S strjust(strvcat(num2str(X(j,i),fmtb),num2str(T(j,i),fmt)))] ;
    end 
    
    B = strvcat(B,S1,A) ;
end 

Q = [];
for j = 1:rows(X)-1 
    Q = strvcat(Q,S1,['              ' strvcat(int2str(j))],'  ') ;
end 

if nargin==2 & lsprt~=0
    Q = strvcat(Q,S1,'L/S','  ');
else
    Q = strvcat(Q,S1,['              ' strvcat(int2str(rows(X)))],'  ') ;
end

Q = strjust(Q);

B = [Q B];
c = [blanks(20),'xret    ', ...
    'alpha'];
for i=1:length(heads)
    c=[c,blanks(9-length(char(heads(i)))),char(heads(i))];
end
c = strjust(c) ;
disp('     ---------------------------------------------------------------------------- ') ;
disp(['              ',www,' portfolio sort, ',char(num2str(res.hperiod)),'-month holding period']) ;
disp(['              Excess returns, alphas, and loadings on:'])
disp(['              ',mdl]) ;

disp('     ---------------------------------------------------------------------------- ') ;

disp([                      c]) ;
disp([                      B]) ;

disp('     ---------------------------------------------------------------------------- ') ;



