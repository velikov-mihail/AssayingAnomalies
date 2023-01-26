function getCOMPUSTATAdditionalData(username, pass, varName, freq)
% PURPOSE: This function downloads additional COMPUSTAT variables. It
% assumes that the original directory structure holds and store the new
% COMPUSTAT Variables in /Data/COMPUSTAT/
%------------------------------------------------------------------------------------------
% USAGE:   
% getCOMPUSTATAdditionalData(username, pass, varName, freq)  % Turns the COMPUSTAT files into matrices
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -username - WRDS username
%        -pass - WRDS password 
%        -varName - cell array of COMPUSTAT variable name(s)
%        -freq - a character array equal to 'annual' or 'quarterly'
%                       indicating the COMPUSTAT file to be used
%------------------------------------------------------------------------------------------
% Output:
%        -None
%------------------------------------------------------------------------------------------
% Examples:
%
% getCOMPUSTATAdditionalData(Params.username,Params.pass,{'ACT'},'annual');
% getCOMPUSTATAdditionalData(Params.username,Params.pass,{'ACT', 'AT'},'annual');
% getCOMPUSTATAdditionalData(Params.username,Params.pass,{'ACTQ'},'quarterly');
% getCOMPUSTATAdditionalData(Params.username,Params.pass,{'ACTQ', 'ATQ'},'quarterly');
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

% Check the variable names and prepare the string for the query
nVarName = length(varName);
varsForQry =varName{1};
if nVarName > 1
    for i=2:nVarName
        varsForQry=[varsForQry, ', ',varName{i}];
    end    
end


% Call the WRDS connection
WRDS = callWRDSConnection(username,pass);

% Load the dates
load dates

% Read the linking file
opts = detectImportOptions('crsp_ccmxpf_lnkhist.csv');
crsp_ccmxpf_lnkhist = readtable('crsp_ccmxpf_lnkhist.csv', opts);

% Filter based on the CCM link
% Leave only link types LC or LU
crsp_ccmxpf_lnkhist = crsp_ccmxpf_lnkhist(ismember(crsp_ccmxpf_lnkhist.linktype, {'LC','LU'}),:);
crsp_ccmxpf_lnkhist = crsp_ccmxpf_lnkhist(:, {'lpermno','gvkey','linkdt','linkenddt'});

% Replace the missing linkeddt with the end of the sample
crsp_ccmxpf_lnkhist.linkenddt(isnat(crsp_ccmxpf_lnkhist.linkenddt)) = datetime(floor(dates(end)/100), 12, 31);

% Store the current directory and navigate to the main directory (i.e., the one that contains the /Library
% Update/ folder
[functionDir,~,~] = fileparts(mfilename('fullpath'));
functionDir = strrep(functionDir, '\', '/');
[startIndex,~] = regexp(functionDir, '/Library Update/');
Params.directory = functionDir(1:startIndex);

% Choose the COMPUSTAT update frequency (annual or qurterly)
switch freq
    case 'annual'
        % Store the query in a character array
        COMPUSTATAnnualQuery = ['select gvkey, datadate, ', varsForQry, ...
                                ' from COMP.funda', ...
                                ' where indfmt=''INDL'' and datafmt=''STD'' and consol=''C'' and popsrc=''D'''];
        
        % Send the query to WRDS
        wrdsTable = fetch(WRDS, COMPUSTATAnnualQuery);
        
        % STore the data and fix the date and gvkeys
        comp_funda = wrdsTable;
        comp_funda.datadate = datetime(comp_funda.datadate);
        comp_funda.gvkey = cellfun(@str2num, comp_funda.gvkey);        

        % Drop observations outside of our sample
        firstYear = floor(dates(1)/100);
        lastYear = floor(dates(end)/100);
        idxToDrop = comp_funda.datadate > datetime(lastYear,12,31) | ...
                    comp_funda.datadate < datetime(firstYear,1,1);
        comp_funda(idxToDrop,:) = [];

        % Merge & clean the COMPUSTAT annual file with CRSP Link history file
        comp_funda_linked = outerjoin(comp_funda, crsp_ccmxpf_lnkhist, 'Type', 'Left', ...
                                                                       'Keys', 'gvkey', ...
                                                                       'MergeKeys',1);
        
        % Fiscal period end date must be within link date range & needs to
        % have permno
        idxToDrop = comp_funda_linked.datadate > comp_funda_linked.linkenddt | ...
                    comp_funda_linked.datadate < comp_funda_linked.linkdt    | ...
                    isnan(comp_funda_linked.lpermno);
        comp_funda_linked(idxToDrop,:) = []; 
    
        % Create the dates variable - align a given fiscal year end with next year's June
        comp_funda_linked.dates = 100*(1+year(comp_funda_linked.datadate)) + 6; 
        
        % Drop a few variables
        comp_funda_linked(:,{'gvkey','linkdt','linkenddt'}) = []; 
        
        % Rename the permno variable
        comp_funda_linked.Properties.VariableNames{'lpermno'} = 'permno';

        % Note: there are cases where a company changes its fiscal year end, which
        % results in more than one observation per permno-year. See, e.g., year
        % 1969 for permno 10006. We'll deal with those here by keeping only the  
        % data from the fiscal year that happens later in the year
        comp_funda_linked = sortrows(comp_funda_linked, {'permno','datadate'});
        
        % Apply the anonymous function (i.e., leaving the last element) in the first argument to every variable, by grouping them by permno & dates
        adjusted_comp_funda_linked = varfun(@(x) x(end), comp_funda_linked, 'GroupingVariables', {'permno','dates'}); 
        
        % Count the number of permno-years with more than 1 row & print
        nduplicates = sum(adjusted_comp_funda_linked.GroupCount > 1); 
        fprintf('There were %d cases of permno-years in which companies moved their fiscal year end.\n', nduplicates); 
        
        % Fix the variable names
        varNames = adjusted_comp_funda_linked.Properties.VariableNames'; 
        clndVarNames = erase(varNames,'Fun_');
        adjusted_comp_funda_linked.Properties.VariableNames = clndVarNames;
        adjusted_comp_funda_linked(:,{'GroupCount','datadate'}) = [];


        % Create the individual variables
        makeCOMPUSTATVariables(Params,adjusted_comp_funda_linked); 
                
    case 'quarterly'
        % Store the query in a character array
        COMPUSTATQuarterlyQuery = ['select gvkey, RDQ, datadate, ',varsForQry, ...
                                   ' from COMP.fundq', ...
                                   ' where indfmt=''INDL'' and datafmt=''STD'' and consol=''C'' and popsrc=''D'''];

        % Send the query to WRDS
        wrdsTable=fetch(WRDS,COMPUSTATQuarterlyQuery);
        
        
        % STore the data and fix the dates and gvkeys
        comp_fundq = wrdsTable;
        comp_fundq.datadate = datetime(comp_fundq.datadate);
        comp_fundq.rdq      = datetime(comp_fundq.rdq);
        comp_fundq.gvkey    = cellfun(@str2num, comp_fundq.gvkey);

        % Drop observations outside of our sample
        firstYear = floor(dates(1)/100);
        lastYear = floor(dates(end)/100);
        idxToDrop = isnat(comp_fundq.rdq)                     | ...
                    comp_fundq.rdq > datetime(lastYear,12,31) | ...
                    comp_fundq.rdq < datetime(firstYear,1,1);        
        comp_fundq(idxToDrop,:) = [];        

        % Merge & clean the COMPUSTAT annual file with CRSP Link history file
        comp_fundq_linked = outerjoin(comp_fundq, crsp_ccmxpf_lnkhist, 'Type', 'Left', ...
                                                                       'Keys', 'gvkey', ...
                                                                       'MergeKeys',1);

        % Fiscal period end date must be within link date range & needs to
        % have permno
        idxToDrop = comp_fundq_linked.datadate > comp_fundq_linked.linkenddt | ...
                    comp_fundq_linked.datadate < comp_fundq_linked.linkdt    | ...
                    isnan(comp_fundq_linked.lpermno);
        comp_fundq_linked(idxToDrop,:)=[]; % Fiscal period end date must be within link date range  

        % Create the dates variable - we'll match based on RDQ   
        comp_fundq_linked.dates = 100 * year(comp_fundq_linked.rdq) + ...
                                        month(comp_fundq_linked.rdq); 
        % Drop a few variables
        comp_fundq_linked(:, {'gvkey','linkdt','linkenddt'}) = [];
        
        % Rename the permno variable
        comp_fundq_linked.Properties.VariableNames{'lpermno'} = 'permno';

        % Note: there are cases where multiple stock-quarter data points are
        % associated with a single earnings announcement date (RDQ). These could be
        % due to restatements, or delays in announcements. See, e.g., permno 63079
        % announcements for 200708 in comp_fundq_linked:
        % temp=comp_fundq_linked(comp_fundq_linked.permno==63079 & comp_fundq_linked.dates==200708,:);
        % We'll deal with these by leaving the latest available fiscal quarter
        % associated with each RDQ
        comp_fundq_linked = sortrows(comp_fundq_linked, {'permno','rdq','datadate'});
        
        % Apply the anonymous function (i.e., leaving the last element) in the first argument to every variable, by grouping them by permno & dates
        adjusted_comp_fundq_linked = varfun(@(x) x(end), comp_fundq_linked, 'GroupingVariables',{'permno','dates'}); 
        
        % Count the number of permno-years with more than 1 row & print
        nduplicates = sum(adjusted_comp_fundq_linked.GroupCount > 1);
        fprintf('There were %d cases of permno-RDQ months associated with multiple quarters.\n', nduplicates); 
        
        % Fix the variable names
        varNames = adjusted_comp_fundq_linked.Properties.VariableNames'; 
        clndVarNames = erase(varNames, 'Fun_');
        adjusted_comp_fundq_linked.Properties.VariableNames = clndVarNames;
        adjusted_comp_fundq_linked(:,{'GroupCount','rdq','datadate'}) = [];

        % Create the individual variables. The third argument tells it it's quarterly variables
        makeCOMPUSTATVariables(Params, adjusted_comp_fundq_linked, 1); 
       
    otherwise 
        error('Wrong COMPUSTAT update frequency. Needs to be ''annual'' or  ''quarterly''.\n\n');
end

close(WRDS);

