function getCOMPUSTATAdditionalData(username,pass,varName,freq)
% PURPOSE: This function uses the stored tables from the COMPUSTAT annual and
% quarterly files to create matrices of dimensions number of months by number
% of stocks for all variables downloaded from COMPUSTAT
%------------------------------------------------------------------------------------------
% USAGE:   
% getCOMPUSTATAdditionalData(Params)              % Turns the COMPUSTAT files into matrices
%------------------------------------------------------------------------------------------
% Required Inputs:
%        -username - WRDS username
%        -pass - WRDS password 
%        -varName - COMPUSTAT variable name(s)
%        -freq - a character array equal to 'annual' or 'quarterly'
%                       indicating the COMPUSTAT file to be used
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

% Call the WRDS connection
WRDS=callWRDSConnection(username,pass);

load dates

% Read the linking file
opts=detectImportOptions('crsp_ccmxpf_lnkhist.csv');
crsp_ccmxpf_lnkhist=readtable('crsp_ccmxpf_lnkhist.csv',opts);

% Filter based on the CCM link
% Leave only link types LC or LU
crsp_ccmxpf_lnkhist=crsp_ccmxpf_lnkhist(ismember(crsp_ccmxpf_lnkhist.linktype,{'LC','LU'}),:);
crsp_ccmxpf_lnkhist=crsp_ccmxpf_lnkhist(:,{'lpermno','gvkey','linkdt','linkenddt'});
% Replace the missing linkeddt with the end of the sample
crsp_ccmxpf_lnkhist.linkenddt(isnat(crsp_ccmxpf_lnkhist.linkenddt))=datetime(floor(dates(end)/100),12,31);

[functionDir,~,~] = fileparts(mfilename('fullpath'));
functionDir=strrep(functionDir,'\','/');
[startIndex,~]=regexp(functionDir,['/Library Update/']);
cd(functionDir(1:startIndex-1))
switch freq
    case 'annual'
        % Get the annual COMPUSTAT data
        COMPUSTATAnnualQuery =['select gvkey, datadate, ',varName,' from COMP.funda where indfmt=''INDL'' and datafmt=''STD'' and consol=''C'' and popsrc=''D'''];
        wrdsTable=fetch(WRDS,COMPUSTATAnnualQuery);
        comp_funda=wrdsTable;
        comp_funda.datadate=datetime(comp_funda.datadate);
        comp_funda.gvkey=cellfun(@str2num,comp_funda.gvkey);        

        % Drop observations outside of our sample
        comp_funda(comp_funda.datadate>datetime(floor(dates(end)/100),12,31) | comp_funda.datadate<datetime(floor(dates(1)/100),1,1),:)=[];

        % Merge & clean the COMPUSTAT annual file with CRSP Link history file
        comp_funda_linked=outerjoin(comp_funda,crsp_ccmxpf_lnkhist,'Type','Left','Keys','gvkey','MergeKeys',1);
        comp_funda_linked(comp_funda_linked.datadate>comp_funda_linked.linkenddt | comp_funda_linked.datadate<comp_funda_linked.linkdt,:)=[]; % Fiscal period end date must be within link date range  
        comp_funda_linked(isnan(comp_funda_linked.lpermno),:)=[]; % Must have permno
        comp_funda_linked.dates=100*(1+year(comp_funda_linked.datadate))+6; % Create the dates variable - align a given fiscal year end with next year's June
        comp_funda_linked(:,{'gvkey','linkdt','linkenddt'})=[]; % Drop a few variables
        comp_funda_linked.Properties.VariableNames{'lpermno'}='permno';

        % Note: there are cases where a company changes its fiscal year end, which
        % results in more than one observation per permno-year. See, e.g., year
        % 1969 for permno 10006. We'll deal with those here by keeping only the  
        % data from the fiscal year that happens later in the year
        comp_funda_linked=sortrows(comp_funda_linked,{'permno','datadate'});
        adjusted_comp_funda_linked=varfun(@(x) x(end),comp_funda_linked,'GroupingVariables',{'permno','dates'}); % Apply the anonymous function (i.e., leaving the last element) in the first argument to every variable, by grouping them by permno & dates
        nduplicates=sum(adjusted_comp_funda_linked.GroupCount>1); % Count the number of permno-years with more than 1 row
        fprintf('There were %d cases of permno-years in which companies moved their fiscal year end.\n',nduplicates); % Let the user know
        varNames=adjusted_comp_funda_linked.Properties.VariableNames'; % Fix the names
        cleanedVarNames=erase(varNames,'Fun_');
        adjusted_comp_funda_linked.Properties.VariableNames=cleanedVarNames;
        adjusted_comp_funda_linked(:,{'GroupCount','datadate'})=[];


        % Create the individual variables
        makeCOMPUSTATVariables(adjusted_comp_funda_linked);
                
    case 'quarterly'
        % Get the quarterly COMPUSTAT data
        COMPUSTATQuarterlyQuery =['select gvkey, RDQ, datadate, ',varName,' from COMP.fundq where indfmt=''INDL'' and datafmt=''STD'' and consol=''C'' and popsrc=''D'''];
        wrdsTable=fetch(WRDS,COMPUSTATQuarterlyQuery);
        comp_fundq=wrdsTable;
        comp_fundq.datadate=datetime(comp_fundq.datadate);
        comp_fundq.rdq=datetime(comp_fundq.rdq);
        comp_fundq.gvkey=cellfun(@str2num,comp_fundq.gvkey);

        % Drop observations outside of our sample
        comp_fundq(isnat(comp_fundq.rdq),:)=[];
        comp_fundq(comp_fundq.rdq>datetime(floor(dates(end)/100),12,31) | comp_fundq.rdq<datetime(floor(dates(1)/100)-1,1,1),:)=[];

        % Merge & clean the COMPUSTAT annual file with CRSP Link history file
        comp_fundq_linked=outerjoin(comp_fundq,crsp_ccmxpf_lnkhist,'Type','Left','Keys','gvkey','MergeKeys',1);
        comp_fundq_linked(comp_fundq_linked.datadate>comp_fundq_linked.linkenddt | comp_fundq_linked.datadate<comp_fundq_linked.linkdt,:)=[]; % Fiscal period end date must be within link date range  
        comp_fundq_linked(isnan(comp_fundq_linked.lpermno),:)=[]; % Must have permno
        comp_fundq_linked.dates=100*year(comp_fundq_linked.rdq)+month(comp_fundq_linked.rdq); % Create the dates variable - align a given fiscal year end with next year's June
        comp_fundq_linked(:,{'gvkey','linkdt','linkenddt'})=[]; % Drop a few variables
        comp_fundq_linked.Properties.VariableNames{'lpermno'}='permno';

        % Note: there are cases where multiple stock-quarter data points are
        % associated with a single earnings announcement date (RDQ). These could be
        % due to restatements, or delays in announcements. See, e.g., permno 63079
        % announcements for 200708 in comp_fundq_linked:
        % temp=comp_fundq_linked(comp_fundq_linked.permno==63079 & comp_fundq_linked.dates==200708,:);
        % We'll deal with these by leaving the latest available fiscal quarter
        % associated with each RDQ
        comp_fundq_linked=sortrows(comp_fundq_linked,{'permno','rdq','datadate'});
        adjusted_comp_fundq_linked=varfun(@(x) x(end),comp_fundq_linked,'GroupingVariables',{'permno','dates'}); % Apply the anonymous function (i.e., leaving the last element) in the first argument to every variable, by grouping them by permno & dates
        nduplicates=sum(adjusted_comp_fundq_linked.GroupCount>1); % Count the number of permno-years with more than 1 row
        fprintf('There were %d cases of permno-RDQ months associated with multiple quarters.\n',nduplicates); % Let the user know
        varNames=adjusted_comp_fundq_linked.Properties.VariableNames'; % Fix the names
        cleanedVarNames=erase(varNames,'Fun_');
        adjusted_comp_fundq_linked.Properties.VariableNames=cleanedVarNames;
        adjusted_comp_fundq_linked(:,{'GroupCount','rdq','datadate'})=[];

        % Create the individual variables
        makeCOMPUSTATVariables(adjusted_comp_fundq_linked,1); % The second argument tells it it's quarterly variables
       
end

cd([currDir]);

close(WRDS);

