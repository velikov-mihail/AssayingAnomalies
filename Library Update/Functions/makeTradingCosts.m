function makeTradingCosts(Params)
% PURPOSE: This function creates the trading costs estimates used in
% Chen and Velikov (2022).
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
%             -Params.tcostsType - type of trading costs to construct: 'full' - low-freq 4-measures combo + TAQ + ISSM; 'lf_combo' - low-freq 4-measures combo; 'gibbs' - just gibbs
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
% Copyright (c) 2022 All rights reserved. 
%       Robert Novy-Marx <robert.novy-marx@simon.rochester.edu>
%       Mihail Velikov <velikov@psu.edu>
% 
%  References
%  1. Chen, A. and M. Velikov, 2022, Zeroing in on the expected return on anomalies, Journal of Financial and Quantitative Analysis, Forthcoming.
%  2. Novy-Marx, R. and M. Velikov, 2022, Assaying anomalies, Working paper.

% Timekeeping
fprintf('\n\n\nNow working on creating the transaction costs. Run started at %s.\n', char(datetime('now')));

% Store the general and daily CRSP data path
dataPath = [Params.directory, 'Data/'];

% Check if correct tcosts input selected
if ~ismember(Params.tcostsType, {'full','lf_combo','gibbs'})
    error('Params.tcostsType needs to be one of the following: ''full'', ''lf_combo'', ''gibbs''.\n');
end

% Check for the Gibbs file
gibbsFileStruct = (dir(fullfile(Params.directory, '**/crspgibbs*.csv')));
if isempty(gibbsFileStruct)
    error(['Gibbs input file does not exists. Gibbs trading cost estimate cannot be constructed.']);
else
    fileName = gibbsFileStruct.name;
end

% Create the Gibbs spreads
effSpreadStruct = struct;
effSpreadStruct.gibbs = makeGibbs(fileName); % Returns 2*c (the full spread). We'll divide by 2 later. Should have crspgibbsYYYY.csv somewhere on the path.
vars = {'gibbs'};

% Check if lf_combo or full costs selected
if ismember(Params.tcostsType, {'lf_combo', 'full'}')
    % Make these measures if so
    effSpreadStruct.hl  = makeCorwinSchultz();
    effSpreadStruct.chl = makeAbdiRanaldi();
    effSpreadStruct.vov = makeKyleObizhaeva();
    vars = [vars {'chl','hl','vov'}];
end

% Check if the full costs measure selected
if strcmp(Params.tcostsType,'full')
    
    % Check for the TAQ file
    hfFileStruct = (dir(fullfile(Params.directory,'**/hf_monthly.csv')));
    if isempty(hfFileStruct)
        error(['High-frequency trading cost input file does not exists. High-frequency trading cost estimate cannot be constructed.']);
    else
        fileName = hfFileStruct.name;
    end    
    hf_spreads = makeHighFreqEffSpreads(fileName);
    effSpreadStruct.hf_spreads_ave = hf_spreads.ave;
    effSpreadStruct.hf_spreads_monthend = hf_spreads.monthend;
    effSpreadStruct.hf_spreads_n = hf_spreads.n;
    vars = [vars {'hf_spreads_ave','hf_spreads_monthend'}];
end

% Store the effective spreads structure
save([dataPath,'effSpreadStruct.mat'],'effSpreadStruct','-v7.3');

% Store filled Gibbs tcosts to compare with Novy-Marx and Velikov (2016)
tcosts = fillMissingTcosts(effSpreadStruct.gibbs/2);
save([dataPath, 'gibbs_filled.mat'], 'tcosts');

% Store some dimensions
nMonths = size(effSpreadStruct.gibbs,1);
nStocks = size(effSpreadStruct.gibbs,2);
nObs    = nMonths * nStocks;
nVars   = length(vars);

% Now create the tcosts. We'll winsorize at the top at 99.9% first
for i = 1:nVars
    % Store this tcost measure's name
    thisVarName = char(vars(i));
    
    % Extract this tcost measure from the struct    
    thisVar = effSpreadStruct.(thisVarName);
    
    % Reshape it to a vector, so that we can winsorize
    rshpdVar = reshape(thisVar,nObs,1);
    
    % Find the finite observations
    idxToWinsor = isfinite(rshpdVar);
    
    % Winsorize & reshape back to matrix form
    rshpdVar(idxToWinsor) = winsor(rshpdVar(idxToWinsor),[0 99.9]);        
    winsoredVar = reshape(rshpdVar, nMonths, nStocks);
    
    % Assign back to the structure
    effSpreadStruct.(thisVarName) = winsoredVar;    
end

% Check if we need to adjust some of the tcost measures
if strcmp(Params.tcostsType,'gibbs')
    % No need to worry about the rest
    effSpreadRaw = effSpreadStruct.gibbs; 
else
    % See Chen and Velikov (2022) for discussion of these
    load dates
    load exchcd
    
    % STore the dates in a matrix
    rptdDates = repmat(dates, 1, nStocks);
    
    % Exluding NASDAQ stocks prior to 1983 for Gibbs and VoV
    idxToRemove = (rptdDates <= 1982212  &  exchcd == 3);
    effSpreadStruct.gibbs(idxToRemove) = nan;
    effSpreadStruct.vov(idxToRemove)   = nan;

    % Exluding NASDAQ stocks prior to 1993 for HL and CHL
    idxToRemove = (rptdDates <= 199212  &  exchcd == 3);
    effSpreadStruct.hl(idxToRemove)  = nan;
    effSpreadStruct.chl(idxToRemove) = nan;

    % Exluding AMEX stocks prior to 1962 for all
    idxToRemove = (rptdDates <= 196112  &  exchcd == 2);
    effSpreadStruct.gibbs(idxToRemove) = nan;
    effSpreadStruct.hl(idxToRemove)    = nan;
    effSpreadStruct.chl(idxToRemove)   = nan;
    effSpreadStruct.vov(idxToRemove)   = nan;        
    
    % Reshape the low-frequency measures
    reshapedLF = [reshape(effSpreadStruct.gibbs, nObs, 1) reshape(effSpreadStruct.hl,  nObs, 1) ...
                  reshape(effSpreadStruct.chl,   nObs, 1) reshape(effSpreadStruct.vov, nObs, 1)];
    
    % Use omitnan here, so that if at least one non-NaN we'll use it        
    reshapedEffSpreadRaw = mean(reshapedLF, 2, 'omitnan'); 
    
    % Check if we also have the high-frequency costs
    if strcmp(Params.tcostsType, 'full')
        % Reshape these too
        reshapedHF = reshape(effSpreadStruct.hf_spreads_ave, nObs, 1);        
        
        % Assign high-frequency spreads wherever we have it
        reshapedEffSpreadRaw(isfinite(reshapedHF)) = reshapedHF(isfinite(reshapedHF));         
    end
    
    % Turn back into a matrix
    effSpreadRaw = reshape(reshapedEffSpreadRaw, nMonths, nStocks); 
end

% Need to divide the effective spreads by 2, because this is the tcost 
% measure (half-spread!!!)
tcosts_raw = effSpreadRaw/2; 

% Store the raw tcosts
save([dataPath, 'tcosts_raw.mat'], 'tcosts_raw');

% Fill in the missing tcosts
tcosts = fillMissingTcosts(tcosts_raw);
save([dataPath, 'tcosts.mat'], 'tcosts');

% Do the FF trading costs calculation here too
makeFFTcosts();
