function makeCOMPUSTATVariables(Params,comp_data,quarterlyIndicator)
% PURPOSE: This function uses the stored tables from the COMPUSTAT annual and
% quarterly files to create matrices of dimensions number of months by number
% of stocks for all variables downloaded from COMPUSTAT
%------------------------------------------------------------------------------------------
% USAGE:   
% makeCOMPUSTATVariables(Params)              % Turns the COMPUSTAT files into matrices
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -Params - a structure containing input parameter values
%             -Params.directory - directory where the setup_library.m was unzipped
%             -Params.username - WRDS username
%             -Params.pass - WRDS password 
%             -Params.domesticCommonEquityShareFlag - flag indicating whether to leave domestic common share equity (share code 10 or 11) only
%             -Params.SAMPLE_START - sample start date
%             -Params.SAMPLE_END - sample end dates
%             -Params.COMPUSTATVariablesFileName - Either name of file ('COMPUSTAT Variable Names.csv' included with library) or 'All' to download all ~1000 COMPUSTAT variables.
%             -Params.driverLocation - location of WRDS PostgreSQL JDBC Driver (included with library)
%             -Params.tcosts - type of trading costs to construct: 'full' - low-freq 4-measures combo + TAQ + ISSM; 'lf_combo' - low-freq 4-measures combo; 'gibbs' - just gibbs
%        -comp_data - a MATLAB table with columns including "permno", "dates", and 
%                       COMPUSTAT data to be stored in the number of months
%                       x number of stocks matrices
%        -quarterlyIndicator - a flag which when equal to 1 indicates that
%                       the function needs to construct data from the
%                       COMPUSTAT quarterly files
%------------------------------------------------------------------------------------------
% Output:
%        -None
%------------------------------------------------------------------------------------------
% Examples:
%
% makeCOMPUSTATVariables(Params)              
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

compustatDirPath=[Params.directory,'Data/COMPUSTAT/'];

load permno
load dates
load ret

n=length(permno)*length(dates);
crsp_mat_link=array2table([reshape(repmat(permno',length(dates),1),n,1) reshape(repmat(dates,1,length(permno)),n,1)],'VariableNames',{'permno','dates'});

varNames=comp_data.Properties.VariableNames';
indVarNames=find(~ismember(varNames,{'permno','dates'}));

for i=1:length(indVarNames)
    thisVarName=char(varNames(indVarNames(i)));   
    fprintf('Now working on COMPUSTAT variable %s, which is %d/%d.\n',upper(thisVarName),i,length(indVarNames));
    tic;
    tempTable=comp_data(:,{'permno','dates',thisVarName});
    mergedTable=outerjoin(crsp_mat_link,tempTable,'Type','Left','MergeKeys',1);
    thisVar=unstack(mergedTable,thisVarName,'dates');
    thisVar.permno=[];
    thisVar=table2array(thisVar)';
    
    if nargin==3
        if quarterlyIndicator==1
            for c = find(sum(isfinite(thisVar),1) > 0)
                mm = find(isfinite(thisVar(:,c)),1,'first');
                MM = find(isfinite(thisVar(:,c)),1,'last');
                for r = mm+1:min(rows(thisVar),MM+2)
                    if isnan(thisVar(r,c))
                        thisVar(r,c) = thisVar(r-1,c);
                    end
                end
            end
        end
    end

    if isequal(size(ret),size(thisVar))
        tempStruct.(upper(thisVarName))=thisVar;
        save([compustatDirPath,upper(thisVarName),'.mat'],'-struct','tempStruct',upper(thisVarName));
    else 
        error('COMPUSTAT variables wrong size.');
    end
    clear tempStruct
    toc;
end
    