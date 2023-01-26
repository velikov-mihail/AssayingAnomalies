function makeTCosts(Params)
% PURPOSE: This function creates the trading costs estimates used in
% Chen and Velikov (2021).
%------------------------------------------------------------------------------------------
% USAGE:   
% makeTCosts(Params)              % Creates the trading costs measures
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
%------------------------------------------------------------------------------------------
% Output:
%        -None
%------------------------------------------------------------------------------------------
% Examples:
%
% makeTCosts(Params)              
%------------------------------------------------------------------------------------------
% Dependencies:
%       Uses getGibbs(), makeCorwinSchultz(), makeAbdiRanaldi(),
%       makeKyleObizhaeva(), getHighFreqMEffSpreads(),
%       fillMissingTcosts(), 
%------------------------------------------------------------------------------------------
% Copyright (c) 2021 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Chen, A. and M. Velikov, 2021, Zeroing in on the expected return on anomalies, Working paper.
%  2. Novy-Marx, R. and M. Velikov, 2021, Assaying anomalies, Working paper.


% Check if the Data\CRSP\daily subdirectory exists. If not, make it
if ~ismember(Params.tcosts,{'full','lf_combo','gibbs'})
    error('Params.tcosts needs to be one of the following: ''full'', ''lf_combo'', ''gibbs''.\n');
end

% Check for the Gibbs file
gibbsFileStruct=(dir(fullfile(Params.directory,'**/crspgibbs*.csv')));
if isempty(gibbsFileStruct)
    error(['Gibbs input file does not exists. Gibbs trading cost estimate cannot be constructed']);
else
    fileName=gibbsFileStruct.name;
end

effSpreadStruct=struct;
effSpreadStruct.gibbs=makeGibbs(fileName); % Returns 2*c (the full spread). We'll divide by 2 later. Should have crspgibbsYYYY.csv somewhere on the path.
vars={'gibbs'};

if ismember(Params.tcosts,{'lf_combo','full'}')
    effSpreadStruct.hl=makeCorwinSchultz();
    effSpreadStruct.chl=makeAbdiRanaldi();
    effSpreadStruct.vov=makeKyleObizhaeva();
    vars=[vars {'chl','hl','vov'}];
end

if strcmp(Params.tcosts,'full')
    effSpreadStruct.hf_spreads=makeHighFreqEffSpreads();
    vars=[vars {'hf_spreads.ave','hf_spreads.monthend'}];
end

save Data/effSpreadStruct effSpreadStruct -v7.3

% Store some dimensions
nummonths=size(effSpreadStruct.gibbs,1);
numstocks=size(effSpreadStruct.gibbs,2);
numobs=nummonths*numstocks;

% Now create the tcosts. We'll winsorize at the top at 99.9% first
for i=1:length(vars)  
    eval(['temp=effSpreadStruct.',char(vars(i)),';']);
    temp2=reshape(temp,numobs,1);
    ind=isfinite(temp2);
    temp2(ind)=winsor(temp2(ind),[0 99.9]);    
    temp3=reshape(temp2,nummonths,numstocks);
    eval(['effSpreadStruct.',char(vars(i)),'=temp3;']);    
end


if strcmp(Params.tcosts,'gibbs')
    effSpreadRaw=effSpreadStruct.gibbs; % No need to worry about the rest
else  % See Chen and Velikov (2021) for discussion of these    
    load dates
    load exchcd
    
    % Exluding NASDAQ stocks prior to 1983 for Gibbs and VoV
    ind=(repmat(dates,1,size(exchcd,2))<=1982212 & exchcd==3);
    effSpreadStruct.gibbs(ind)=nan;
    effSpreadStruct.vov(ind)=nan;

    % Exluding NASDAQ stocks prior to 1993 for HL and CHL
    ind=(repmat(dates,1,size(exchcd,2))<=199212 & exchcd==3);
    effSpreadStruct.hl(ind)=nan;
    effSpreadStruct.chl(ind)=nan;

    % Exluding AMEX stocks prior to 1962 for all
    ind=(repmat(dates,1,size(exchcd,2))<=196112 & exchcd==2);
    effSpreadStruct.gibbs(ind)=nan;
    effSpreadStruct.hl(ind)=nan;
    effSpreadStruct.chl(ind)=nan;
    effSpreadStruct.vov(ind)=nan;        
    
    reshapedLF=[reshape(effSpreadStruct.gibbs,numobs,1) reshape(effSpreadStruct.hl,numobs,1) ...
                reshape(effSpreadStruct.chl,numobs,1) reshape(effSpreadStruct.vov,numobs,1)];
    reshapedEffSpreadRaw=nanmean(reshapedLF,2); % Use nanmean here, so that if at least one non-NaN we'll use it
    if strcmp(Params.tcosts,'full')
        reshapedHF=reshape(effSpreadStruct.hf_spreads.ave,numobs,1);        
        reshapedEffSpreadRaw(isfinite(reshapedHF))=reshapedHF(isfinite(reshapedHF)); % Assign high-frequency spreads wherever we have it        
    end
    effSpreadRaw=reshape(reshapedEffSpreadRaw,nummonths,numstocks); % Turn back into a matrix 
end

tcosts_raw=effSpreadRaw/2; % Need to divide by 2, because this is the tcost measure (half-spread!!!)

save Data/tcosts_raw tcosts_raw

tcosts=fillMissingTcosts(tcosts_raw);
save Data/tcosts tcosts

tcosts=fillMissingTcosts(effSpreadStruct.gibbs/2);
save Data/gibbs_filled tcosts



