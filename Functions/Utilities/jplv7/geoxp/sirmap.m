function [out,Rbar,tstat]=sirmap(long,lat,xinp,yinp,nbcla,varargin)
% PURPOSE: This function links a map and one or two SIR scatterplots
%--------------------------------------------------------------
% USAGE: out = sirmap(long,lat,xinp,yinp,nbcla,direct,carte,label,symbol)
%   where:
%          long = n x 1 vector of coordinates on the first axis
%           lat = n x 1 vector of coordinates on the second axis
%          xinp = explanatory variable (matrix n x p)  
%          yinp = n x 1 vector of the dependent variable
%          nbcla = number of classes
%          direct = optionnal 2x1 vector of integers or integer corresponding to the order of the edr directions selected for the plot. Default is [1;2]
%          carte = n x 2 optionnal matrix giving the polygons of the edges of the spatial units
%          label = n x 1 optionnal variable used to label selected observations
%          symbol = * symbol=1 : selected spatial units are marked with a different symbol
%                   * symbol=0 : selected spatial units are marked with a different color only (default)
%--------------------------------------------------------------
% OUTPUTS: out = (n x 1) 0-1 variable: selected spatial units are marked with a 1  
%--------------------------------------------------------------
% MANUAL: Select points on either the map or the scatterplots by clicking with the left mouse button
%         You can select points inside a polygon: - right click to set the first point of the polygon
%                                                 - left click to set the other points
%                                                 - right click to close the polygon
%         Selection is lost when you switch graph
%         To quit, click the middle button or press 'q'
% -----------------------------------------------------------------------
% uses sirf.m, fastbinsmooth.m, setdens4.m, ols.m, selectmap.m, selectstat.m
%------------------------------------------------------------------------
% Christine Thomas-Agnan, Anne Ruiz-Gazen, Julien Moutel
% June 2003
% Université de Toulouse I, Toulouse, France
% cthomas@cict.fr-



close all;
figure(1);
set(figure(1),'Units','Normalized','Position',[0.0031 0.0957 0.9945 0.7539]);
set(figure(1),'Units','Pixel');
obs=zeros(size(long,1),1);
c=0;
l=0;
symbol=0;
global direct;
global yinpglob;
yinpglob=yinp;
direct=[1,2];
vectx=[];
vecty=[];
name1=inputname(3);
name2=inputname(4);
%creation of a menu to save
labels= str2mat(...
    '&File', ...
    '>&Save' ...
    );
calls= str2mat(...
    '',...
    'save sirfich  out -ascii' ...
    );
makemenu(figure(1),labels,calls);
%%%%%%%%%%%%%%%%%%%%%%%

% handle the optionnal parameters
if ~isempty(varargin)
    t=size(varargin,2);
    if ~isempty(varargin{1})
        direct=varargin{1};
        if length(direct)>2
            direct=direct(1:2);
        end;
    end;
    if  t>=2 & ~isempty(varargin{2})
        carte=varargin{2};
        c=1;
    end;
    if  t>=3 & ~isempty(varargin{3})
        label=varargin{3};
        l=1;
    end;
    if t==4 & ~isempty(varargin{4})
        symbol=varargin{4};
    end;
end;
%%%%%%%%%%%%%%%%%%%%%

% Trace the map
Axis1=subplot(1,2,1);
if c==1
    plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
end;
hold on;
plot(long,lat,'b.');
axis equal;
title('Map');
Xlim1=get(Axis1,'XLim');
Ylim1=get(Axis1,'YLim');
axis manual;
%%%%%%%%%%%%%%%%%%%%%

if length(direct)==1
    Axis2=subplot(1,2,2);
elseif length(direct)==2
    Axis2=subplot(2,2,2);
    Axis3=subplot(2,2,4);
end;

% Call to sirf
[xindex, beta, valp]= sirf(xinp,yinp,nbcla);
%%%%%%%%%%%%%%
global vardir1;

global h1;
global Hslide1;
global Ht1;
global r1;
global eval1;
subplot(Axis2);
vardir1=xindex(:,direct(1));

plot(vardir1,yinp,'b.');
xlabel(['edr direction ',num2str(direct(1))]);
ylabel(name2);
h1=0.4*(max(vardir1)-min(vardir1))/2;
eval1=[min(vardir1):(max(vardir1)-min(vardir1))/200:max(vardir1)]';
warning off;
r1=fastbinsmooth([vardir1';yinpglob'],h1,[min(vardir1),max(vardir1)],201,2,3,0,1);
warning on;
hold on;
plot(eval1,r1,'k-');
hold off;
axis manual;
if length(direct)==2
    global vardir2;
    global Hslide2;
    global Ht2;
    global h2;
    global r2;
    global eval2;
    vardir2=xindex(:,direct(2));
    subplot(Axis3);
    plot(vardir2,yinp,'b.');
    xlabel(['edr direction ',num2str(direct(2))]);
    ylabel(name2);
    h2=0.4*(max(vardir2)-min(vardir2))/2;
    eval2=[min(vardir2):(max(vardir2)-min(vardir2))/200:max(vardir2)]';
    warning off;
    r2=fastbinsmooth([vardir2';yinpglob'],h2,[min(vardir2),max(vardir2)],201,2,3,0,1);
    warning on;
    hold on;
    plot(eval2,r2,'k-');
    hold off;
    axis manual;
end;


% Create the sliders
Hslide1=uicontrol('Style','slider','Min',0,'Max',100,'Value',40);
Ht1=uicontrol('Style','text','String',['a1=' num2str(get(Hslide1,'Value')),'%'],'Position',[100,20,60,20],'Enable','inactive');
set(Hslide1,'Callback','setdens4'); % Call to setdens4.m when one of the sliders is clicked
if length(direct)==2
    Hslide2=uicontrol('Style','slider','Min',0,'Max',100,'Value',40,'Position',[300,20,60,20]);
    Ht2=uicontrol('Style','text','String',['a2=' num2str(get(Hslide2,'Value')),'%'],'Position',[380,20,60,20],'Enable','inactive');
    set(Hslide2,'Callback','setdens4');
end;
%%%%%%%%%%%%%%%%%%%%

figure(2);
set(figure(2),'Units','Normalized','Position',[0.0031 0.0957 0.9945 0.7539]);
set(figure(2),'Units','Pixel');
endxinp=size(xinp,2);
if endxinp>4
    endxinp=4;
end;
if length(direct)==1
    plotmatrix([vardir1 xinp(:,1:4)]);
    %xlabel(['direction ',num2str(direct(1))]);
    title(['edr direction ',num2str(direct(1))]);
elseif length(direct)==2
%     A1=subplot(1,2,1);
%     plotmatrix([vardir1 xinp(:,1:4)]);
%     %xlabel(['direction ',num2str(direct(1))]);
%     title(['edr direction ',num2str(direct(1))]);
%     A2=subplot(1,2,2);
%     plotmatrix([vardir2 xinp(:,1:4)]);
%     %xlabel(['direction ',num2str(direct(2))]);
%     title(['edr direction ',num2str(direct(2))]);
    plotmatrix([vardir1 vardir2 xinp(:,1:endxinp)]);
    title(['edr direction ',num2str(direct(1)),' & edr direction ',num2str(direct(2))]);
end;

endxinp=size(xinp,2);
Rbar=zeros(1,endxinp);
tstat=zeros(endxinp-1,endxinp);
for i=1:endxinp
  premcol=xinp(:,1);
  coli=xinp(:,i);
  XX=xinp;
  XX(:,1)=coli;
   XX(:,i)=premcol;
   results=ols(xindex(:,1),XX(:,2:endxinp));
   Rbar(i)=results.rbar;
   tstat(:,i)=results.tstat;
end

figure(1);
% Main loop
maptest=0;
sirtest1=0;
if length(direct)==2
    sirtest2=0;
end;
BUTTON=0;
while BUTTON~=2 & BUTTON~=113 % Stop when the user push the middle button or press 'q'
    Posfig=get(1,'Position');
    PosAx1=get(Axis1,'Position');
    PosAx2=get(Axis2,'Position');
    if length(direct)==2
        PosAx3=get(Axis3,'Position');
    end;
    %redraw the graphs
    subplot(Axis2);
    hold on;
    cla;
    Iselect=find(obs==1);
    Iunselect=find(obs==0);
    if ~isempty(Iunselect)
      plot(vardir1(Iunselect),yinp(Iunselect),'b.');
    end;
%     if opt==2
         plot(eval1',r1,'k');
%     end;
%     if opt==3
%         for i=1:length(quantiles)
%             plot(evalv1,quanti(:,i),'y');
%         end;
%     end;
    if ~isempty(Iselect)
        if maptest==1
            if symbol==1
                plot(vardir1(Iselect),yinp(Iselect),'r*');
            else
                plot(vardir1(Iselect),yinp(Iselect),'r.');
            end;
        elseif sirtest1==1
            if symbol==1
                plot(vardir1(Iselect),yinp(Iselect),'mo');
            else
                plot(vardir1(Iselect),yinp(Iselect),'m.'); 
            end;
            if ~isempty(vectx)
                plot(vectx,vecty,'k');
            end;
        elseif sirtest2==1
            if symbol==1
                plot(vardir1(Iselect),yinp(Iselect),'gd');
            else
                plot(vardir1(Iselect),yinp(Iselect),'g.');
            end;
        end;
    end;
    
    hold off;
    if length(direct)==2
        subplot(Axis3);
        hold on;
        cla;
%     if opt==2
        plot(eval2',r2,'k');
%     end;
%     if opt==3
%         for i=1:length(quantiles)
%             plot(evalv1,quanti(:,i),'y');
%         end;
%     end;
        if ~isempty(Iunselect)
        plot(vardir2(Iunselect),yinp(Iunselect),'b.');
        end;
        if ~isempty(Iselect)
            if maptest==1
                if symbol==1
                    plot(vardir2(Iselect),yinp(Iselect),'r*');
                else
                    plot(vardir2(Iselect),yinp(Iselect),'r.');
                end;
            elseif sirtest1==1
                if symbol==1
                    plot(vardir2(Iselect),yinp(Iselect),'mo');
                else
                    plot(vardir2(Iselect),yinp(Iselect),'m.'); 
                end;
            elseif sirtest2==1
                if symbol==1
                    plot(vardir2(Iselect),yinp(Iselect),'gd');
                else
                    plot(vardir2(Iselect),yinp(Iselect),'g.');
                end;
                if ~isempty(vectx)
                    plot(vectx,vecty,'k');
                end;
            end;
        end;
        
    hold off;
    end;
    subplot(Axis1);
    hold on;
    cla;
   
    if c==1
        plot(carte(:,1),carte(:,2),'Color',[0.8 0.5 0.6]);
    end;
    if ~isempty(Iunselect)
      plot(long(Iunselect),lat(Iunselect),'b.');
    end;
    if ~isempty(Iselect)
        if maptest==1
            if symbol==1
                plot(long(Iselect),lat(Iselect),'r*');
            else
                plot(long(Iselect),lat(Iselect),'r.');
            end;
            if ~isempty(vectx)
                plot(vectx,vecty,'k');
            end;
        elseif sirtest1==1
            if symbol==1
                plot(long(Iselect),lat(Iselect),'mo');
            else
                plot(long(Iselect),lat(Iselect),'m.');
            end;
        elseif sirtest2==1
            if symbol==1
                plot(long(Iselect),lat(Iselect),'gd');
            else
                plot(long(Iselect),lat(Iselect),'g.');
            end;
        end;
        if l==1
            Htex=text(long(Iselect),lat(Iselect),num2str(label(Iselect)));
            set(Htex,'FontSize',8);
        end;
    end;   
    
    hold off;
    %%%%%%%%%%%%%%%%%%%%%%%%%%%%%
    
    [x,y,BUTTON]=ginput(1);
    currentpoint=get(1,'CurrentPoint');
    % map selection
    if (currentpoint(1)>=PosAx1(1)*Posfig(3)) & (currentpoint(1)<=(PosAx1(1)+PosAx1(3))*Posfig(3)) & (currentpoint(2)>=PosAx1(2)*Posfig(4)) & (currentpoint(2)<=(PosAx1(2)+PosAx1(4))*Posfig(4))
        if maptest==0      
            maptest=1;
            sirtest1=0;
            if length(direct)==2
                sirtest2=0;
            end;
            obs=zeros(size(long,1),1);
        end;
        % point selection
        if BUTTON~=3 & BUTTON~=2 
            [obs,vectx,vecty]=selectmap(lat,long,obs,x,y,'point');   
        %%%%%%%%%%%%%%%%%%
        % polygon selection
        elseif BUTTON==3 
            [obs,vectx,vecty]=selectmap(lat,long,obs,x,y,'poly');
        end;
        %%%%%%%%%%%%%%%%%%%
    %%%%%%%%%%%%%%%%%%%%%%%
    % scatterplot1 selection
    elseif (currentpoint(1)>=PosAx2(1)*Posfig(3)) & (currentpoint(1)<=(PosAx2(1)+PosAx2(3))*Posfig(3)) & (currentpoint(2)>=PosAx2(2)*Posfig(4)) & (currentpoint(2)<=(PosAx2(2)+PosAx2(4))*Posfig(4))
        if sirtest1==0
            sirtest1=1;
            maptest=0;
            if length(direct)==2
                sirtest2=0;
            end;
            obs=zeros(size(long,1),1);
        end;
        % point selection
        if BUTTON~=3 & BUTTON~=2 
            obs=selectstat('scatter',obs,vardir1,'point',yinp,x,y);
        %%%%%%%%%%%%%%%%%%
        % polygon selection
        elseif BUTTON==3 
            [obs,vectx,vecty]=selectstat('scatter',obs,vardir1,'poly',yinp,x,y);
        end;
        %%%%%%%%%%%%%%%%%%%%
    % scatterplot2 selection
    elseif length(direct)==2 & (currentpoint(1)>=PosAx3(1)*Posfig(3)) & (currentpoint(1)<=(PosAx3(1)+PosAx3(3))*Posfig(3)) & (currentpoint(2)>=PosAx3(2)*Posfig(4)) & (currentpoint(2)<=(PosAx3(2)+PosAx3(4))*Posfig(4))
        if sirtest2==0
            sirtest2=1;
            maptest=0;
            sirtest1=0;
            obs=zeros(size(long,1),1);
        end;
        % point selection
        if BUTTON~=3 & BUTTON~=2 
            obs=selectstat('scatter',obs,vardir2,'point',yinp,x,y);
        %%%%%%%%%%%%%%%%%%
        % polygon selection
        elseif BUTTON==3 
            [obs,vectx,vecty]=selectstat('scatter',obs,vardir2,'poly',yinp,x,y);
        end;
        %%%%%%%%%%%%%%%%%%%%
    end;
    %%%%%%%%%%%%%%%%%%%%%%
end;
out=obs;
%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%%