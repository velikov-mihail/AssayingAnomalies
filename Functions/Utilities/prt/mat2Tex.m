function mat2Tex(coeffs,varargin)
% PURPOSE: This function prints out latex table output for a standard table
% of estimates based on a matrix of coefficients, an optional matrix of signicance 
% statistics (t-stats, s.e., p-values)
%------------------------------------------------------------------------------------------
% USAGE:   
%      mat2Tex(coeffs)            produces latex output where A is the
%                                  matrix that contains the coefficient,
%                                  tA is the matrix with the t-stats, and h
%                                  is the vector of headers
%      mat2Tex(coeffs,'Name','Value')             produces latex output for matrix A
%                                  without printing out t-stats
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -coeffs - a matrix of coefficients estimates                                  
% Optional Name-Value Pair Arguments:
%        -'sigstats' - a matrix of significant statistics (e.g., t-stats,
%                           standard errors, p-values) to be printed below coefficients in
%                           brackets
%        -'rowHeaders' - a cell array of strings indicating the headers for each row
%        -'decimals' - number of decimal points to print
%        -'bracketsType' - type of brackets to use: '[' (default), '(', '{'
%------------------------------------------------------------------------------------------
% Output:
%        - N/A 
%------------------------------------------------------------------------------------------
% Examples:
%
% mat2Tex(coeffs)                                         % print coefficients only
% mat2Tex(coeffs,'sigstats',tstats)                       % print coefficients & t-stats
% mat2Tex(coeffs,'sigstats',stderrors)                    % print coefficients & std errors
% mat2Tex(coeffs,'rowHeaders',headers)                    % add row headers in first column
% mat2Tex(coeffs,'decimals',1)                            % only 1 decimal
% mat2Tex(coeffs,'bracketsType','(')                      % use parentheses instead of 
%                                                            square brackets
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
%------------------------------------------------------------------------------------------

% Parse the inputs
expectedBracketsTypes={'[','(','{'};

p=inputParser;
validNum=@(x) isnumeric(x);
validCellstr=@(x) iscellstr(x);
validBracketType=@(x) ismember(x,expectedBracketsTypes);
addRequired(p,'coeffs',validNum);
addOptional(p,'sigstats',coeffs,validNum);
addOptional(p,'rowHeaders',{},validCellstr);
addOptional(p,'decimals',2,validNum);
addOptional(p,'bracketsType','[',validBracketType);
addOptional(p,'colFormatSpec',{},validCellstr);
parse(p,coeffs,varargin{:});


sigstats=p.Results.sigstats;
rowHeaders=p.Results.rowHeaders;
decimals=p.Results.decimals;
bracketsType=p.Results.bracketsType;
colFormatSpec=p.Results.colFormatSpec;

indSigStats=(nansum(nansum(coeffs-sigstats))~=0);

fprintf('\n\n');
for i=1:size(coeffs,1)
    if ~isempty(rowHeaders)
        fprintf('%s',char(rowHeaders(i)));
    end
    for j=1:size(coeffs,2)
        if isempty(colFormatSpec)
            formatSpec=['%.',char(num2str(decimals)),'f'];
        else 
            formatSpec=char(colFormatSpec(j));
        end
        if isnan(coeffs(i,j))
           fprintf(' & ');
        else
            eval(['fprintf('' & ',formatSpec,''',coeffs(i,j));']);
        end
    end
    if indSigStats
        fprintf('\\\\[-1pt]\n');
    else
        fprintf('\\\\[2pt]\n');       
    end        
    if indSigStats
        for j=1:size(coeffs,2)

            if isempty(colFormatSpec)
                formatSpec=['%.',char(num2str(decimals)),'f'];
            else 
                formatSpec=char(colFormatSpec(j));
            end
                                    
            if isnan(sigstats(i,j))
                fprintf(' & ');
            else
                switch bracketsType
                    case '['
                        eval(['fprintf('' & [',formatSpec,']'',sigstats(i,j));']);                        
                    case '('
                        eval(['fprintf('' & (',formatSpec,')'',sigstats(i,j));']);
                    case '{'
                        eval(['fprintf('' & {',formatSpec,'}'',sigstats(i,j));']);
                end
            end
        end
        fprintf('\\\\[2pt]\n');       
    end
end
fprintf('\n\n');

