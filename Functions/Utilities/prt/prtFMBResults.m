function prtFMBResults(p, bhat, t)
% PURPOSE: Utility function to optionally print results by runFamaMacBeth()
%------------------------------------------------------------------------------------------
% USAGE:   
% prtFMBResults(p, bhat, t)
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -p - parsed input object from runFamaMacBeth
%        -bhat - vector of coefficient estimates from runFamaMacBeth
%        -t - vector of t-statistics estimated from runFamaMacBeth
%------------------------------------------------------------------------------------------
% Output:
%        -N/A
%------------------------------------------------------------------------------------------
% Examples:
%
% prtFMBResults(p, bhat, t)
%------------------------------------------------------------------------------------------
% Dependencies:
%       Used by runFamaMacBeth()
%------------------------------------------------------------------------------------------
% Copyright (c) 2023 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Novy-Marx, R. and M. Velikov, 2023, Assaying anomalies, Working paper.

if p.Results.noConst==0
    nX = length(bhat)-1;
else
    nX = length(bhat);
end

in.rnames='';
if ~isempty(p.Results.labels)        
    nchar = max(cellfun(@(x) length(char(x)), p.Results.labels));
    for i=1:length(p.Results.labels)
        clabel = char(p.Results.labels(i));
        nclabel = length(clabel);
        in.rnames = [in.rnames;[blanks(25-nclabel-(nchar-nclabel+1)),clabel,blanks(nchar-nclabel+1)]];
    end
else
    for i=1:nX
        in.rnames = [in.rnames;['                    var ' int2str(i)]];
    end
    
    if p.Results.noConst==0     % If we have a  constant
        in.rnames = ['                    var 0'; ...
                     in.rnames];
    end
end
in.rnames = [blanks(25); in.rnames];
in.fmt = '%12.3f';

fprintf('---------------------------------------------------------------------- \n')
fprintf('           Results from Fama - MacBeth regressions \n')
fprintf('---------------------------------------------------------------------- \n')
m = [bhat' t'];
in.cnames = ['Coeff ';'t-stat'];
mprint(m,in)
fprintf('---------------------------------------------------------------------- \n')



